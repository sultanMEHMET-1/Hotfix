"""Deterministic execution and request-independent transactional recovery."""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import math
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from contracts.api_types import RecoveryError, WorkflowExecutionResponse, WorkflowSummary
from . import build, custom
from .config import BackendError, Settings, load_workflows, prune_runs, read_json, referenced_fields, validator, write_allowed
from .recovery import Recovery
from .reset import committed_selectors, restore_original
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
            # Logs stay searchable in Sentry, but only our own fingerprinted events become issues.
            # Otherwise every ERROR line (ours, Browser Use, Google) is a separate issue, and one
            # failed recovery opens six of them.
            integrations=[LoggingIntegration(capture_sentry_logs=True, level=logging.INFO, event_level=None)],
            # Profiles run while a sampled trace is active, so both the 0.4 s fast path and a heal are profiled.
            profile_session_sample_rate=1.0, profile_lifecycle="trace",
        )
        app.state.configuration_error = None
        app.state.drafts = custom.Drafts()
        app.state.author_busy = False
        app.state.building = set()
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
            for workflow_id, (definition, _, _) in list(app.state.workflows.items()):
                try:
                    store = SelectorStore(settings, workflow_id)
                    selector_map = store.read()
                    if selector_map["workflow_id"] != workflow_id:
                        raise ValueError("A selector map belongs to another workflow")
                    if not referenced_fields(definition) <= set(selector_map["fields"]):
                        raise ValueError("A workflow references unknown selector fields")
                except Exception:
                    if not workflow_id.startswith("custom-"):
                        raise
                    log.warning("Skipping created workflow %s: its selector map is missing or does not match", workflow_id)
                    del app.state.workflows[workflow_id]
                    continue
                app.state.stores[workflow_id] = store
            for workflow_id, store in app.state.stores.items():
                async with store.lock(exclusive=True):
                    restored = store.recover_inflight()
                if restored is not None:
                    log.warning("Interrupted recovery for %s: baseline restored as selector version %s", workflow_id,
                                restored, extra={"phase": "ROLLBACK"})
                    sentry_sdk.capture_event({"level": "warning", "fingerprint": ["mender.crash-recovery", workflow_id],
                                              "message": f"Interrupted recovery for {workflow_id}: baseline restored"})
            pruned = prune_runs(settings.root / "runs")
            if pruned:
                log.info("Pruned %s old failure-artifact folders", pruned)
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
        raw = await request.body()
        try:
            body = json.loads(raw) if raw.strip() else {}
        except ValueError:
            raise HTTPException(422, "Body must be JSON")
        if not isinstance(body, dict) or not isinstance(body.get("workflow"), (str, type(None))):
            raise HTTPException(422, "Body must be an object with an optional string 'workflow'")
        target = body.get("workflow")
        if target is not None and target not in app.state.stores:
            raise HTTPException(404, "Unknown workflow")
        names = [target] if target else sorted(app.state.stores)
        recovery = app.state.recovery
        if any(recovery.active(name) for name in names):
            raise HTTPException(409, "A recovery is running; retry when it finishes")
        # Fetch every committed map first, so a map missing from git cannot leave some workflows reset.
        try:
            originals = {name: await committed_selectors(settings, name) for name in names}
        except Exception:
            log.exception("Reset failed")
            sentry_sdk.capture_exception()
            raise HTTPException(500, "Reset failed before any change; see backend logs")
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
                versions[name] = restore_original(store, originals[name])
            except Exception:
                log.exception("Reset failed")
                sentry_sdk.capture_exception()
                raise HTTPException(500, "Reset failed; see backend logs")
            finally:
                await lock.__aexit__(None, None, None)
            recovery.cooldown.pop(name, None)
            build.clear(settings, name)
        log.info("Original selectors restored (%s); cooldown cleared", versions, extra={"phase": "ROLLBACK"})
        default = getattr(app.state, "default_workflow", None)
        return {"version": versions.get(default) or next(iter(versions.values()), None), "versions": versions,
                "blocked": app.state.configuration_error}

    class DraftRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        site: str = Field(max_length=20)
        request: str = Field(max_length=600)

    def summary(name):
        definition = app.state.workflows[name][0]
        return WorkflowSummary(id=name, goal=definition.goal, mutates=definition.mutates, default=False,
                               params_schema=definition.params_schema, example_params=definition.canary.params)

    @app.post("/api/v1/workflows/draft")
    async def create_draft(body: DraftRequest, request: Request):
        """Describe a read-only workflow in a sentence; returns a preview to keep or discard. Spends model money."""
        require_local(request)
        if app.state.configuration_error:
            raise HTTPException(503, app.state.configuration_error)
        if app.state.author_busy:
            raise HTTPException(409, {"code": "busy", "message": "Another workflow is being created"})
        try:
            app.state.drafts.check_quota(app)
        except BackendError as exc:
            raise HTTPException(422, {"code": exc.code, "message": str(exc)}) from exc
        app.state.author_busy = True
        try:
            from . import author  # imported here so the fast path never loads the model code
            draft = await author.draft(settings, body.site, body.request)
        except BackendError as exc:
            if exc.code not in author.FREE_REFUSALS:  # a refusal before any model call costs nothing, so it is not counted
                app.state.drafts.count_attempt()
            log.warning("Workflow creation failed: %s", exc.code)
            status = {"model_unconfigured": 503, "author_timeout": 504, "agent_error": 502}.get(exc.code, 422)
            raise HTTPException(status, {"code": exc.code, "message": str(exc)}) from exc
        finally:
            app.state.author_busy = False
        app.state.drafts.count_attempt()
        return custom.view(app.state.drafts.add(draft), draft)

    @app.post("/api/v1/workflows/draft/{token}/accept", response_model=WorkflowSummary)
    async def accept_draft(token: str, request: Request):
        require_local(request)
        draft = app.state.drafts.get(token)
        if draft is None:
            raise HTTPException(404, {"code": "no_draft", "message": "That preview expired; create it again"})
        if len(custom.custom_ids(app)) >= custom.MAX_CUSTOM:  # checked first, so the preview survives and can be kept later
            raise HTTPException(422, {"code": "quota_total", "message": "Delete a created workflow first"})
        try:
            custom.keep(app, settings, draft)
        except Exception as exc:
            log.exception("Could not keep a created workflow")
            sentry_sdk.capture_exception()
            raise HTTPException(500, {"code": "keep_failed", "message": "The workflow could not be saved"}) from exc
        app.state.drafts.discard(token)
        return summary(draft.id)

    @app.delete("/api/v1/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str, request: Request):
        require_local(request)
        if not workflow_id.startswith("custom-") or workflow_id not in app.state.workflows:
            raise HTTPException(404, "Only created workflows can be deleted")
        if app.state.recovery.active(workflow_id):
            raise HTTPException(409, "A recovery is running; retry when it finishes")
        # Runs hold the selector lock while they execute, so wait for them instead of pulling files out from under one.
        lock = app.state.stores[workflow_id].lock(exclusive=True)
        try:
            async with asyncio.timeout(settings.lock_timeout):
                await lock.__aenter__()
        except TimeoutError:
            raise HTTPException(409, "A run is in progress; retry when it finishes")
        try:
            custom.remove(app, settings, workflow_id)
        finally:
            await lock.__aexit__(None, None, None)
        return {"deleted": workflow_id}

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
                built_cost = built_ms = None
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
                                if request.workflow in build.BUILD_ON_FIRST_RUN and result.failure is not None and result.failure.failed_step in selectors["fields"] \
                                        and request.params != workflow.canary.params:
                                    # The known-good canary tells a broken selector from a bad input (a typo, a course that does
                                    # not exist). The first needs an agent run; the second must never cost one.
                                    probe_lock = store.lock()
                                    async with asyncio.timeout(settings.lock_timeout):
                                        await probe_lock.__aenter__()
                                    try:
                                        probe = await runner.execute(request.workflow, workflow.canary.params, output_validator)
                                    finally:
                                        await probe_lock.__aexit__(None, None, None)
                                    if probe.data is not None:
                                        raise BackendError("input_not_found", "The page works for a known input but returned nothing for these values. Check what you typed.")
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
                    if data and not attempted and not build.is_built(settings, request.workflow) \
                            and request.workflow not in app.state.building:
                        # First successful run of an unbuilt endpoint: a real agent confirms what the selectors read.
                        app.state.building.add(request.workflow)
                        try:
                            with sentry_sdk.start_span(op="workflow.build", name="verified first run"):
                                log.info("Building %s: agent verifies the first run", request.workflow, extra={"phase": "BUILD"})
                                url = build.page_url(settings, store.read(), request.params)
                                built_cost, built_ms = await build.verify(settings, workflow, url, data)
                            build.mark_built(settings, request.workflow, params=request.params, cost_usd=built_cost, duration_ms=built_ms)
                            attempted = True
                        finally:
                            app.state.building.discard(request.workflow)
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
                    agent_cost_usd=built_cost if built_cost is not None else (outcome.agent_cost_usd if owner and outcome else None),
                    agent_duration_ms=built_ms if built_ms is not None else (outcome.agent_duration_ms if owner and outcome else None),
                    cooldown_remaining_s=cooldown_remaining,
                )
                payload = response.model_dump(mode="json", exclude_none=True)
                if not records:
                    payload.pop("heal_records")
                app.state.response_validator.validate(payload)
                return JSONResponse(payload)

    return app


app = create_app()
