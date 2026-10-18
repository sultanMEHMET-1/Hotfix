"""Deterministic execution and request-independent transactional recovery."""

import asyncio
from contextlib import asynccontextmanager
import logging
import math
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from contracts.api_types import RecoveryError, WorkflowExecutionResponse, WorkflowSummary
from .config import BackendError, Settings, load_workflows, read_json, validator, write_allowed
from .recovery import Recovery
from .reset import restore_original
from .runner import Runner
from .store import SelectorStore
from .terminal import configure_logging


log = logging.getLogger("mender.backend")
log.setLevel(logging.INFO)


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    params: dict


def capture_failure(workflow_id, result):
    failure = result.failure
    fingerprint = ["mender.runner", workflow_id]
    if failure:
        fingerprint.extend([failure.failed_step, failure.expected_selector])
        sentry_sdk.set_tag("old_selector", failure.expected_selector)
        sentry_sdk.set_context("runner.failure", failure.model_dump())
    else:
        fingerprint.append(result.error.code)
    sentry_sdk.capture_event({
        "level": "error", "message": str(result.error), "fingerprint": fingerprint,
    })


def referenced_fields(definition):
    return {step.field for step in definition.steps} | {output.field for output in definition.outputs.values()}


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        sentry_sdk.init(
            traces_sample_rate=1.0, enable_logs=True, include_local_variables=False,
            # Logs stay searchable in Sentry, but only our own fingerprinted events become issues.
            # Otherwise every ERROR line (ours, Browser Use, Google) is a separate issue, and one
            # failed recovery opens six of them.
            integrations=[LoggingIntegration(capture_sentry_logs=True, level=logging.INFO, event_level=None)],
        )
        app.state.configuration_error = None
        app.state.diagnose = None
        try:
            timeouts = (settings.runner_timeout, settings.agent_timeout, settings.recovery_timeout,
                        settings.cleanup_reserve, settings.lock_timeout)
            if any(not math.isfinite(value) or value <= 0 for value in timeouts):
                raise ValueError("Timeouts must be positive")
            if settings.cleanup_reserve >= settings.recovery_timeout:
                raise ValueError("Cleanup reserve must be shorter than recovery timeout")
            app.state.workflows = load_workflows(settings)
            app.state.stores = {}
            for workflow_id, (definition, _, _) in app.state.workflows.items():
                store = SelectorStore(settings, workflow_id)
                selector_map = store.read()
                if selector_map["workflow_id"] != workflow_id:
                    raise ValueError("A selector map belongs to another workflow")
                if not referenced_fields(definition) <= set(selector_map["fields"]):
                    raise ValueError("A workflow references unknown selector fields")
                app.state.stores[workflow_id] = store
            if settings.demo_workflow and settings.demo_workflow not in app.state.workflows:
                raise ValueError("Configured default workflow definition is missing")
            names = sorted(app.state.workflows)
            app.state.default_workflow = settings.demo_workflow or (
                "permit-application" if "permit-application" in names else (names[0] if names else None))
            app.state.runner = Runner(settings)
            app.state.response_validator = validator(read_json(
                settings.root / "contracts/workflow_execution_response.schema.json"
            ))
        except Exception:
            app.state.configuration_error = "Invalid backend configuration; check workflow definitions and contracts"
            log.exception("Backend configuration failed")
            sentry_sdk.capture_exception()
        app.state.recovery = Recovery(app, settings)
        try:
            yield
        finally:
            await app.state.recovery.drain()

    app = FastAPI(title="Mender backend", lifespan=lifespan)

    def require_local(request: Request):
        forwarded = "x-forwarded-for" in request.headers or "forwarded" in request.headers
        if forwarded or not request.client or request.client.host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Operator endpoints are local only")

    @app.get("/api/v1/status")
    async def status(request: Request):
        require_local(request)
        recovery = app.state.recovery
        now = recovery.clock()
        return {"blocked": app.state.configuration_error,
                "active": sorted(w for w in recovery.tasks if recovery.active(w)),
                "cooldown": {w: round(entry["expires"] - now, 3) for w, entry in recovery.cooldown.items()
                             if entry["expires"] > now}}

    @app.get("/api/v1/workflows", response_model=list[WorkflowSummary])
    async def workflows():
        """What this backend can run, so a UI can offer it. The default workflow is listed first."""
        if app.state.configuration_error:
            raise HTTPException(503, app.state.configuration_error)
        default = app.state.default_workflow
        order = sorted(app.state.workflows, key=lambda name: (name != default, name))
        return [WorkflowSummary(id=name, goal=app.state.workflows[name][0].goal,
                                mutates=app.state.workflows[name][0].mutates, default=name == default,
                                params_schema=app.state.workflows[name][0].params_schema,
                                example_params=app.state.workflows[name][0].canary.params) for name in order]

    @app.post("/api/v1/admin/reset")
    async def reset(request: Request):
        """Rehearsal reset: restore committed selectors (one workflow or all) and forget its failure cooldown."""
        require_local(request)
        if app.state.configuration_error and not getattr(app.state, "stores", None):
            raise HTTPException(503, app.state.configuration_error)
        try:
            body = await request.json()
        except ValueError:
            body = {}
        target = body.get("workflow") if isinstance(body, dict) else None
        if target is not None and target not in app.state.stores:
            raise HTTPException(404, "Unknown workflow")
        names = [target] if target else sorted(app.state.stores)
        recovery = app.state.recovery
        if any(recovery.active(name) for name in names):
            raise HTTPException(409, "A recovery is running; retry when it finishes")
        versions = {}
        # One workflow at a time, never nested, so two resets cannot deadlock against each other.
        for name in names:
            store = app.state.stores[name]
            lock = store.lock(exclusive=True)
            try:
                async with asyncio.timeout(settings.lock_timeout):
                    await lock.__aenter__()
            except TimeoutError:
                raise HTTPException(409, "Selector map busy")
            try:
                versions[name] = await restore_original(settings, store)
            except Exception:
                log.exception("Reset failed")
                sentry_sdk.capture_exception()
                raise HTTPException(500, "Reset failed; see backend logs")
            finally:
                await lock.__aexit__(None, None, None)
            recovery.cooldown.pop(name, None)
        log.info("Original selectors restored (%s); cooldown cleared", versions, extra={"phase": "ROLLBACK"})
        default = app.state.default_workflow
        return {"version": versions.get(default) or next(iter(versions.values())), "versions": versions,
                "blocked": app.state.configuration_error}

    @app.post("/api/v1/run-workflow", response_model=WorkflowExecutionResponse)
    async def run_workflow(request: WorkflowRequest):
        start = time.monotonic()
        if app.state.configuration_error:
            raise HTTPException(503, app.state.configuration_error)
        if not app.state.workflows:
            raise HTTPException(503, "No workflow definitions configured")
        if request.workflow not in app.state.workflows:
            raise HTTPException(404, "Unknown workflow")
        workflow, params_validator, output_validator = app.state.workflows[request.workflow]
        if not params_validator.is_valid(request.params):
            raise HTTPException(422, "Parameters do not match the workflow schema")
        if not settings.script.is_file():
            raise HTTPException(503, "The runner script is unavailable")
        store, runner = app.state.stores[request.workflow], app.state.runner
        with sentry_sdk.isolation_scope():
            sentry_sdk.set_tag("workflow", request.workflow)
            sentry_sdk.set_tag("mode", "fast")
            sentry_sdk.set_tag("tier", "deterministic")
            with sentry_sdk.start_span(op="workflow.execute", name="run-workflow") as span:
                log.info("Running workflow %s", request.workflow, extra={"phase": "FAST"})
                trace_id = span.trace_id
                attempted = False
                diff = None
                error = None
                data = {}
                records = []
                cooldown_remaining = None
                owner = False
                outcome = None
                recovery = app.state.recovery
                try:
                    task = recovery.active(request.workflow)
                    if task is None:
                        lock = store.lock()
                        locked = False
                        try:
                            async with asyncio.timeout(settings.lock_timeout):
                                await lock.__aenter__()
                            locked = True
                        except TimeoutError:
                            task = recovery.active(request.workflow)
                            if task is None:
                                raise BackendError("lock_timeout", "Selector map busy; fast-path lock wait exceeded")
                        if locked:
                            try:
                                if app.state.configuration_error:
                                    raise HTTPException(503, app.state.configuration_error)
                                selectors = store.read()
                                if selectors["workflow_id"] != request.workflow:
                                    raise HTTPException(503, "The selector map belongs to another workflow")
                                if not referenced_fields(workflow) <= set(selectors["fields"]):
                                    raise HTTPException(503, "Workflow steps reference unknown selector fields")
                                if workflow.mutates and not write_allowed(selectors["target_url"], settings.write_hosts):
                                    raise BackendError("write_not_allowed", "This workflow changes data, so it only runs against local or allowlisted sites")
                                result = await runner.execute(request.workflow, request.params, output_validator)
                            finally:
                                await lock.__aexit__(None, None, None)
                            if result.data is not None:
                                data = result.data
                            else:
                                capture_failure(request.workflow, result)
                                log.warning("%s", result.error, extra={"phase": "BROKEN"})
                                if result.failure is None:
                                    raise result.error
                                if result.failure.failed_step not in selectors["fields"]:
                                    # E.g. the page did not load: there is no selector to repair.
                                    raise BackendError("runner_failed", "The runner failed at a step that is not a selector, such as loading the page")
                                # No await from here to start(): lookup, join and register are atomic.
                                task = recovery.active(request.workflow)
                                if task is None:
                                    hit = recovery.cached(request.workflow, result.failure, selectors)
                                    if hit:
                                        attempted, outcome = True, hit["outcome"]
                                        cooldown_remaining = max(0.0, hit["expires"] - recovery.clock())
                                        log.warning("Cached failure from recovery %s; %.1f s remaining", hit["recovery_id"],
                                                    hit["expires"] - recovery.clock(), extra={"phase": "COOLDOWN"})
                                    else:
                                        owner = True
                                        task = recovery.start(request.workflow, workflow, request.params,
                                                              output_validator, selectors, result)
                    if task is not None:
                        attempted = True
                        outcome = await asyncio.shield(task)
                        attempted = outcome.attempted
                    if outcome is not None:
                        span.set_data("recovery.trace_id", outcome.trace_id)
                        # Records describe the selector transaction; status describes this caller's run.
                        records = outcome.records
                        if outcome.error:
                            raise outcome.error
                    if task is not None:
                        diff = outcome.diff
                        if owner:
                            data = outcome.data
                        else:
                            # Shared healing is verified once; each waiter still gets its own output.
                            async with asyncio.timeout(settings.lock_timeout):
                                lock = store.lock()
                                await lock.__aenter__()
                            try:
                                own = await runner.execute(request.workflow, request.params, output_validator)
                            finally:
                                await lock.__aexit__(None, None, None)
                            if own.data is None:
                                raise own.error
                            data = own.data
                except TimeoutError:
                    error = BackendError("lock_timeout", "Selector map busy; fast-path lock wait exceeded")
                except BackendError as exc:
                    error = exc
                    if exc.code in {"browser_cleanup_failed", "runner_cleanup_failed", "model_cleanup_failed"}:
                        app.state.configuration_error = str(exc)
                except HTTPException:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception:
                    sentry_sdk.capture_exception()
                    error = BackendError("execution_failed", "Workflow execution failed")
                success = error is None
                healed = bool(diff) and success
                if error:
                    log.error("%s: %s", error.code, error, extra={"phase": "FAILED"})
                sentry_sdk.set_tag("mode", "healed" if attempted else "fast")
                sentry_sdk.set_tag("heal_success", healed)
                log.log(logging.INFO if success else logging.WARNING, "Workflow %s in %.2f s",
                        "verified" if success else "failed", time.monotonic() - start,
                        extra={"phase": "HEALED" if healed else ("FAST" if success else "FAILED")})
                span.set_status("ok" if success else "internal_error")
                response = WorkflowExecutionResponse(
                    status="healed" if healed else ("success" if success else "failed"),
                    execution_time_ms=(time.monotonic() - start) * 1000,
                    data=data if success else {}, healed=healed, trace_id=trace_id,
                    diff=diff if success else None, recovery_attempted=attempted,
                    error=RecoveryError(code=error.code, message=str(error)) if error else None,
                    heal_records=records,
                    # Measurements belong to the request that ran the agent, never waiters or cache hits.
                    agent_cost_usd=outcome.agent_cost_usd if owner and outcome else None,
                    agent_duration_ms=outcome.agent_duration_ms if owner and outcome else None,
                    cooldown_remaining_s=cooldown_remaining,
                )
                payload = response.model_dump(mode="json", exclude_none=True)
                if not records:
                    payload.pop("heal_records")
                app.state.response_validator.validate(payload)
                return JSONResponse(payload)

    return app


app = create_app()
