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

from contracts.api_types import RecoveryError, WorkflowExecutionResponse
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


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        sentry_sdk.init(
            traces_sample_rate=1.0, enable_logs=True, include_local_variables=False,
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
            app.state.store = SelectorStore(settings)
            selector_map = app.state.store.read()
            demo_id = settings.demo_workflow or selector_map["workflow_id"]
            if settings.demo_workflow and demo_id not in app.state.workflows:
                raise ValueError("Configured demo workflow definition is missing")
            if demo_id in app.state.workflows and app.state.workflows[demo_id][0].canary is None:
                raise ValueError("The demo workflow requires a canary")
            app.state.runner = Runner(settings)
            app.state.response_validator = validator(read_json(
                settings.root / "contracts/workflow_execution_response.schema.json"
            ))
        except Exception:
            app.state.configuration_error = "Invalid backend configuration; check workflow definitions and contracts"
            log.exception("Backend configuration failed")
        app.state.recovery = Recovery(app, settings)
        try:
            yield
        finally:
            await app.state.recovery.drain()

    app = FastAPI(title="Mender backend", lifespan=lifespan)

    def require_local(request: Request):
        if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
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

    @app.post("/api/v1/admin/reset")
    async def reset(request: Request):
        """Rehearsal reset: restore the committed selectors and forget the failure cooldown."""
        require_local(request)
        if app.state.configuration_error and not hasattr(app.state, "store"):
            raise HTTPException(503, app.state.configuration_error)
        recovery = app.state.recovery
        if any(recovery.active(workflow) for workflow in list(recovery.tasks)):
            raise HTTPException(409, "A recovery is running; retry when it finishes")
        try:
            async with asyncio.timeout(settings.lock_timeout):
                lock = app.state.store.lock(exclusive=True)
                await lock.__aenter__()
        except TimeoutError:
            raise HTTPException(409, "Selector map busy")
        try:
            version = await restore_original(settings, app.state.store)
        except Exception:
            log.exception("Reset failed")
            raise HTTPException(500, "Reset failed; see backend logs")
        finally:
            await lock.__aexit__(None, None, None)
        recovery.cooldown.clear()
        log.info("Original selectors restored as version %s; cooldown cleared", version, extra={"phase": "ROLLBACK"})
        return {"version": version, "blocked": app.state.configuration_error}

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
        store, runner = app.state.store, app.state.runner
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
                                if not all(step.field in selectors["fields"] for step in workflow.steps):
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
                                # No await from here to start(): lookup, join and register are atomic.
                                task = recovery.active(request.workflow)
                                if task is None:
                                    hit = recovery.cached(request.workflow, result.failure, selectors)
                                    if hit:
                                        attempted, outcome = True, hit["outcome"]
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
                )
                payload = response.model_dump(mode="json", exclude_none=True)
                if not records:
                    payload.pop("heal_records")
                app.state.response_validator.validate(payload)
                return JSONResponse(payload)

    return app


app = create_app()
