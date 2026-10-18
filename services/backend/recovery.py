"""M2 recovery: active tasks outlive requests; provisional maps stay locked."""

import asyncio
from dataclasses import dataclass
import importlib
import logging
import math
import os
import platform
from importlib.metadata import version as package_version
from urllib.parse import urlsplit
from uuid import uuid4

import sentry_sdk

from contracts.api_types import SelectorDiff
from .config import BackendError, masked_output
from .store import atomic_json


log = logging.getLogger("mender.backend")
RETRYABLE = {"agent_error", "agent_timeout", "agent_no_result"}


@dataclass
class RecoveryResult:
    data: dict | None = None
    diff: SelectorDiff | None = None
    error: BackendError | None = None
    attempted: bool = False
    trace_id: str | None = None


def validate_failure(workflow_id, workflow, selectors, result):
    if selectors["workflow_id"] != workflow_id:
        raise BackendError("invalid_failure", "Selector map belongs to another workflow")
    failure = result.failure
    if failure is None:
        raise result.error or BackendError("invalid_failure", "No failure evidence")
    if failure.workflow_id != workflow_id:
        raise BackendError("invalid_failure", "Failure belongs to another workflow")
    if selectors["fields"].get(failure.failed_step) != failure.expected_selector:
        raise BackendError("stale_failure", "Failure does not match the current selector map")
    position = next((i for i, step in enumerate(workflow.steps) if step.field == failure.failed_step), None)
    if position is None:
        raise BackendError("unmapped_step", "Failed step is absent from ordered workflow steps")
    if urlsplit(failure.page_url)[:2] != urlsplit(selectors["target_url"])[:2]:
        raise BackendError("unexpected_page", "Failure page does not match the configured portal origin")
    return position


class Recovery:
    def __init__(self, app, settings):
        self.app = app
        self.settings = settings
        # ponytail: only active tasks; cooldown and persistent flight history belong to M3.
        self.tasks = {}

    def active(self, workflow_id):
        task = self.tasks.get(workflow_id)
        return task if task and not task.done() else None

    def start(self, workflow_id, workflow, params, output_validator, selectors, result):
        task = self.active(workflow_id)
        if task is None:
            started = asyncio.get_running_loop().time()
            task = asyncio.create_task(self.run(
                workflow_id, workflow, params, output_validator, selectors, result, started
            ), name=f"recovery:{workflow_id}")
            self.tasks[workflow_id] = task

            def finished(completed):
                if self.tasks.get(workflow_id) is completed:
                    del self.tasks[workflow_id]

            task.add_done_callback(finished)
        return task

    async def drain(self):
        if self.tasks:
            await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)

    async def run(self, workflow_id, workflow, params, output_validator, selectors, result, started):
        clock = asyncio.get_running_loop().time
        hard_deadline = started + self.settings.recovery_timeout
        deadline = hard_deadline - self.settings.cleanup_reserve
        store, runner = self.app.state.store, self.app.state.runner
        outcome = RecoveryResult()
        metrics = []
        recovery_id = str(uuid4())
        baseline = None
        installed = False
        committed = False
        lock = store.lock(exclusive=True)
        locked = False
        with sentry_sdk.isolation_scope():
            sentry_sdk.set_tag("workflow", workflow_id)
            sentry_sdk.set_tag("mode", "healed")
            sentry_sdk.set_tag("tier", "agent")
            parent = sentry_sdk.get_current_span()
            trace = {"trace_id": parent.trace_id, "parent_span_id": parent.span_id} if parent else {}
            # A separate transaction can finish/export even after the request span closes.
            with sentry_sdk.start_transaction(op="healer.recovery", name="Transactional recovery", **trace) as span:
                outcome.trace_id = span.trace_id
                try:
                    async with asyncio.timeout_at(deadline):
                        await lock.__aenter__()
                    locked = True
                    async with asyncio.timeout_at(deadline):
                        if self.app.state.configuration_error:
                            raise BackendError("backend_unavailable", self.app.state.configuration_error)
                        baseline = store.read()
                        if baseline != selectors:
                            result = await runner.execute(workflow_id, params, output_validator, deadline=deadline)
                        if result.data is not None:
                            outcome.data = result.data
                        else:
                            validate_failure(workflow_id, workflow, baseline, result)
                            store.backup(result.run_id, baseline)
                            current = baseline
                            outcome.attempted = True
                            diagnose = self.app.state.diagnose
                            if diagnose is None:
                                module = await asyncio.to_thread(importlib.import_module, ".healer", __package__)
                                diagnose = module.diagnose
                            for attempt in range(1, 4):
                                if clock() >= deadline:
                                    raise TimeoutError()
                                position = validate_failure(workflow_id, workflow, current, result)
                                failure = result.failure
                                sentry_sdk.set_tag("old_selector", failure.expected_selector)
                                sentry_sdk.set_context("runner.failure", failure.model_dump())
                                log.info("Attempt %s/3: Browser Use engaged for %s", attempt, failure.failed_step,
                                         extra={"phase": "AGENT"})
                                candidate = None
                                invocation_started = clock()
                                try:
                                    with sentry_sdk.start_span(op="healer.diagnose", name="Browser Use diagnosis"):
                                        candidate = await diagnose(self.settings, workflow, params, failure, deadline=deadline)
                                    if candidate is None:
                                        raise BackendError("agent_no_result", "Browser Use returned no result")
                                except BackendError as exc:
                                    metrics.append({**getattr(exc, "agent_metrics", {}), "attempt": attempt,
                                                    "wall_time_ms": (clock() - invocation_started) * 1000})
                                    log.warning("Attempt %s: %s: %s", attempt, exc.code, exc,
                                                extra={"phase": "FAILED"})
                                    if exc.code not in RETRYABLE or attempt == 3 or clock() >= deadline:
                                        raise
                                    continue
                                except BaseException:
                                    metrics.append({"attempt": attempt, "wall_time_ms": (clock() - invocation_started) * 1000})
                                    raise
                                metrics.append({**candidate.metrics, "attempt": attempt,
                                                "wall_time_ms": (clock() - invocation_started) * 1000})
                                if clock() >= deadline:
                                    raise TimeoutError()
                                if not isinstance(candidate.selector, str) or not candidate.selector.strip() or candidate.selector == failure.expected_selector:
                                    raise BackendError("invalid_candidate", "Healer did not propose a replacement selector")
                                sentry_sdk.set_tag("new_selector", candidate.selector)
                                with sentry_sdk.start_span(op="healer.patch", name="Patch and deterministic verification"):
                                    patched = {**current, "fields": {**current["fields"], failure.failed_step: candidate.selector},
                                               "version": current["version"] + 1}
                                    sentry_sdk.get_current_span().set_data("healer.evidence", candidate.evidence.model_dump())
                                    store.write(patched)
                                    installed = True
                                    current = patched
                                    log.info("%s: %s -> %s (provisional version %s)", failure.failed_step,
                                             failure.expected_selector, candidate.selector, current["version"], extra={"phase": "PATCH"})
                                    # Already exclusively locked: Runner.execute never acquires a store lock.
                                    replay = await runner.execute(workflow_id, params, output_validator, deadline=deadline)
                                    if replay.data is None:
                                        if replay.failure:
                                            sentry_sdk.set_context("runner.replay_failure", replay.failure.model_dump())
                                        later = validate_failure(workflow_id, workflow, current, replay)
                                        if later <= position:
                                            raise BackendError("verification_failed", "Replay failed at the same or an earlier step")
                                        if attempt == 3:
                                            raise BackendError("attempts_exhausted", "Three agent invocations exhausted")
                                        log.info("Replay advanced from step %s to %s", position, later, extra={"phase": "VERIFY"})
                                        result = replay
                                        continue
                                    log.info("Deterministic replay and output schema passed", extra={"phase": "VERIFY"})
                                    if workflow.canary:
                                        canary = await runner.execute(workflow_id, workflow.canary.params, output_validator, deadline=deadline)
                                        if canary.data is None or masked_output(canary.data, workflow.canary.ignore_paths) != masked_output(
                                            workflow.canary.expected_output, workflow.canary.ignore_paths
                                        ):
                                            raise BackendError("canary_failed", "Canary rejected provisional selectors")
                                        log.info("Known lookup matched expected output", extra={"phase": "CANARY"})
                                    # No await between final verification and marking committed.
                                    if clock() >= deadline:
                                        raise TimeoutError()
                                    outcome.data = replay.data
                                    outcome.diff = SelectorDiff(old_selector=failure.expected_selector, new_selector=candidate.selector)
                                    committed = True
                                    break
                except TimeoutError:
                    outcome.error = BackendError("recovery_timeout", "Recovery work deadline expired")
                except BackendError as exc:
                    outcome.error = exc
                except asyncio.CancelledError:
                    outcome.error = BackendError("recovery_cancelled", "Recovery cancelled during server shutdown")
                    raise
                except Exception:
                    sentry_sdk.capture_exception()
                    outcome.error = BackendError("recovery_failed", "Unexpected recovery failure")
                finally:
                    if installed and not committed:
                        try:
                            version = store.restore(baseline)
                            log.warning("Baseline restored as version %s", version, extra={"phase": "ROLLBACK"})
                            if clock() >= hard_deadline:
                                self.app.state.configuration_error = "Recovery exceeded its cleanup deadline; inspect owned processes before restarting"
                                outcome.error = BackendError("cleanup_timeout", self.app.state.configuration_error)
                        except Exception:
                            self.app.state.configuration_error = "Rollback failed; restore the backup and restart the backend"
                            outcome.error = BackendError("rollback_failed", self.app.state.configuration_error)
                            sentry_sdk.capture_exception()
                    if locked:
                        await lock.__aexit__(None, None, None)
                    if outcome.error and outcome.error.code in {"browser_cleanup_failed", "runner_cleanup_failed", "model_cleanup_failed"}:
                        self.app.state.configuration_error = str(outcome.error)
                    if outcome.error:
                        log.error("%s: %s", outcome.error.code, outcome.error, extra={"phase": "FAILED"})
                        failed = result.failure
                        sentry_sdk.capture_event({"level": "error", "message": str(outcome.error),
                                                 "fingerprint": ["mender.recovery", workflow_id, outcome.error.code,
                                                                 failed.failed_step if failed else "unknown",
                                                                 failed.expected_selector if failed else "unknown"]})
                    report = {"recovery_id": recovery_id, "workflow": workflow_id,
                              "model": os.getenv("GEMINI_MODEL"), "python": platform.python_version(),
                              "browser_use": package_version("browser-use"), "wall_time_ms": (clock() - started) * 1000,
                              "success": outcome.error is None, "error_code": outcome.error.code if outcome.error else None,
                              "attempts": metrics}
                    totals = {}
                    for key in ("prompt_tokens", "completion_tokens", "cached_prompt_tokens", "total_tokens", "cost_usd"):
                        values = [entry.get(key) for entry in metrics]
                        known = [value for value in values if isinstance(value, (int, float)) and math.isfinite(value)]
                        if known:
                            totals[key] = sum(known)
                        totals[key + "_complete"] = bool(values) and len(known) == len(values)
                    report["totals"] = totals
                    sentry_sdk.set_context("recovery.measurements", report)
                    span.set_data("recovery.measurements", report)
                    sentry_sdk.set_tag("heal_success", committed)
                    span.set_status("ok" if outcome.error is None else "internal_error")
                    tokens = str(totals.get("total_tokens", "unknown"))
                    if "total_tokens" in totals and not totals["total_tokens_complete"]:
                        tokens += " (partial)"
                    cost = f"${totals['cost_usd']:.6f}" if "cost_usd" in totals else "unknown"
                    if "cost_usd" in totals and not totals["cost_usd_complete"]:
                        cost += " (partial)"
                    log.info("Recovery %.3f s; %s invocations; tokens %s; estimated cost %s",
                             report["wall_time_ms"] / 1000, len(metrics), tokens, cost,
                             extra={"phase": "METRICS", "recovery_measurements": report})
                    try:
                        atomic_json(self.settings.backend / "state" / f"recovery-{recovery_id}.json", report)
                    except OSError:
                        log.exception("Could not retain recovery measurements")
                return outcome
