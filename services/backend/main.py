"""Deterministic execution and request-independent transactional recovery."""

import asyncio
from contextlib import asynccontextmanager
import logging
import math
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
import sentry_sdk

from contracts.api_types import WorkflowExecutionResponse
from .config import BackendError, Settings, load_workflows, read_json, validator
from .recovery import Recovery
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

    @app.post("/api/v1/run-workflow", response_model=WorkflowExecutionResponse,
              response_model_exclude_none=True, response_model_exclude_defaults=True,
              response_model_exclude={"error", "agent_cost_usd", "agent_duration_ms", "heal_records"})
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
                recovery = app.state.recovery
                try:
                    task = recovery.active(request.workflow)
                    owner = False
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
                                owner = recovery.active(request.workflow) is None
                                task = recovery.start(request.workflow, workflow, request.params, output_validator, selectors, result)
                    if task is not None:
                        attempted = True
                        outcome = await asyncio.shield(task)
                        attempted = outcome.attempted
                        span.set_data("recovery.trace_id", outcome.trace_id)
                        if outcome.error:
                            raise outcome.error
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
                )
                app.state.response_validator.validate(response.model_dump(exclude_none=True))
                return response

    return app


app = create_app()
