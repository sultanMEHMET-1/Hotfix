"""M1: one broken field, deterministic verification, and rollback."""

import asyncio
from contextlib import asynccontextmanager
import importlib
import logging
import math
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
import sentry_sdk

from contracts.api_types import RecoveryError, SelectorDiff, WorkflowExecutionResponse
from .config import BackendError, Settings, load_workflows, masked_output, read_json, validator
from .runner import Runner
from .store import SelectorStore


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
        sentry_sdk.init(
            traces_sample_rate=1.0, enable_logs=True, include_local_variables=False,
        )
        app.state.configuration_error = None
        app.state.diagnose = None
        try:
            if any(not math.isfinite(value) or value <= 0 for value in (settings.runner_timeout, settings.agent_timeout)):
                raise ValueError("Timeouts must be positive")
            app.state.workflows = load_workflows(settings)
            app.state.store = SelectorStore(settings)
            app.state.store.read()
            app.state.runner = Runner(settings)
            app.state.response_validator = validator(read_json(
                settings.root / "contracts/workflow_execution_response.schema.json"
            ))
        except Exception:
            app.state.configuration_error = "Invalid backend configuration; check workflow definitions and contracts"
            log.exception("Backend configuration failed")
        yield

    app = FastAPI(title="Mender backend", lifespan=lifespan)

    @app.post("/api/v1/run-workflow", response_model=WorkflowExecutionResponse,
              response_model_exclude_none=True, response_model_exclude_defaults=True)
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
                trace_id = span.trace_id
                attempted = False
                candidate = None
                diff = None
                error = None
                data = {}
                try:
                    async with store.lock():
                        if app.state.configuration_error:
                            raise HTTPException(503, app.state.configuration_error)
                        selectors = store.read()
                        if selectors["workflow_id"] != request.workflow:
                            raise HTTPException(503, "The selector map belongs to another workflow")
                        if not all(step.field in selectors["fields"] for step in workflow.steps):
                            raise HTTPException(503, "Workflow steps reference unknown selector fields")
                        result = await runner.execute(request.workflow, request.params, output_validator)
                    if result.data is not None:
                        data = result.data
                    else:
                        capture_failure(request.workflow, result)
                        if result.failure is None:
                            raise result.error
                        # ponytail: one selector map, so serialize M1 repairs; M3 adds shared flights.
                        async with store.lock(exclusive=True):
                            baseline = store.read()
                            if baseline != selectors:
                                result = await runner.execute(request.workflow, request.params, output_validator)
                            if result.data is not None:
                                data = result.data
                            else:
                                if not result.failure:
                                    raise result.error
                                failure = result.failure
                                if baseline["fields"].get(failure.failed_step) != failure.expected_selector:
                                    raise BackendError("stale_failure", "Failure does not match the current selector map")
                                if failure.failed_step not in {step.field for step in workflow.steps}:
                                    raise BackendError("unmapped_step", "Failed step is absent from ordered workflow steps")
                                if urlsplit(failure.page_url)[:2] != urlsplit(baseline["target_url"])[:2]:
                                    raise BackendError("unexpected_page", "Failure page does not match the configured portal origin")
                                store.backup(result.run_id, baseline)
                                attempted = True
                                sentry_sdk.set_tag("mode", "healed")
                                sentry_sdk.set_tag("tier", "agent")
                                sentry_sdk.add_breadcrumb(category="healer", message="Browser Use Agent Engaged")
                                diagnose = app.state.diagnose
                                if diagnose is None:
                                    module = await asyncio.to_thread(importlib.import_module, ".healer", __package__)
                                    diagnose = module.diagnose
                                with sentry_sdk.start_span(op="healer.diagnose", name="Browser Use diagnosis"):
                                    candidate = await diagnose(settings, workflow, request.params, failure)
                                if candidate.selector == failure.expected_selector or not candidate.selector.strip():
                                    raise BackendError("invalid_candidate", "Healer did not propose a replacement selector")
                                sentry_sdk.set_tag("new_selector", candidate.selector)
                                installed = False
                                try:
                                    with sentry_sdk.start_span(op="healer.patch", name="Patch and deterministic verification"):
                                        patched = {**baseline, "fields": {**baseline["fields"],
                                                   failure.failed_step: candidate.selector},
                                                   "version": baseline["version"] + 1}
                                        store.write(patched)
                                        installed = True
                                        replay = await runner.execute(request.workflow, request.params, output_validator)
                                        if replay.data is None:
                                            raise BackendError("verification_failed", "Deterministic replay rejected the replacement; baseline restored")
                                        if workflow.canary:
                                            canary = await runner.execute(request.workflow, workflow.canary.params, output_validator)
                                            if canary.data is None or masked_output(canary.data, workflow.canary.ignore_paths) != masked_output(
                                                workflow.canary.expected_output, workflow.canary.ignore_paths
                                            ):
                                                raise BackendError("canary_failed", "Canary rejected the replacement; baseline restored")
                                        data = replay.data
                                        diff = SelectorDiff(old_selector=failure.expected_selector, new_selector=candidate.selector)
                                except BaseException:
                                    if installed:
                                        try:
                                            store.restore(baseline)
                                        except Exception as rollback_error:
                                            app.state.configuration_error = "Rollback failed; restore the baseline backup before restarting the backend"
                                            raise BackendError("rollback_failed", app.state.configuration_error) from rollback_error
                                    raise
                except BackendError as exc:
                    error = RecoveryError(code=exc.code, message=str(exc))
                except HTTPException:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception:
                    sentry_sdk.capture_exception()
                    error = RecoveryError(code="recovery_failed", message="Recovery failed; inspect the Sentry trace")
                success = error is None
                sentry_sdk.set_tag("heal_success", bool(diff) and success)
                if attempted:
                    log.log(logging.INFO if success else logging.WARNING, "Browser Use recovery finished", extra={
                        "workflow": request.workflow, "mode": "healed", "heal_success": bool(diff) and success,
                        "old_selector": result.failure.expected_selector if result.failure else None,
                        "new_selector": candidate.selector if candidate else None,
                        "error_code": error.code if error else None,
                    })
                if diff:
                    sentry_sdk.set_tag("new_selector", diff.new_selector)
                span.set_status("ok" if success else "internal_error")
                response = WorkflowExecutionResponse(
                    status="healed" if diff else ("success" if success else "failed"),
                    execution_time_ms=(time.monotonic() - start) * 1000,
                    data=data if success else {}, healed=bool(diff), trace_id=trace_id,
                    diff=diff, recovery_attempted=attempted, error=error,
                    agent_cost_usd=candidate.cost_usd if candidate else None,
                    agent_duration_ms=candidate.duration_ms if candidate else None,
                )
                app.state.response_validator.validate(response.model_dump(exclude_none=True))
                return response

    return app


app = create_app()
