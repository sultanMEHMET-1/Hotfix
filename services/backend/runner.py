"""The agreed runner CLI and failure-artifact boundary."""

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
from uuid import uuid4

import jsonschema
import sentry_sdk

from contracts.api_types import FailurePayload
from .config import BackendError, Settings, read_json, validator


@dataclass
class RunResult:
    run_id: str
    data: dict | None = None
    failure: FailurePayload | None = None
    error: BackendError | None = None


def reject_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


async def stop_process(process, timeout=5):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=max(0.001, timeout))
    except TimeoutError as exc:
        raise BackendError("runner_cleanup_failed", "Runner process could not be reaped") from exc


def parse_timings(stderr: str):
    """Phase timings the runner prints as `runner_timings_ms={"launch": ..}`; anything malformed is ignored."""
    for line in reversed(stderr.splitlines()):
        if line.startswith("runner_timings_ms="):
            try:
                value = json.loads(line.split("=", 1)[1])
            except ValueError:
                return {}
            return {k: float(v) for k, v in value.items() if isinstance(v, (int, float)) and k.isidentifier()}
    return {}


class Runner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.failure_validator = validator(
            read_json(settings.root / "contracts/failure_payload.schema.json")
        )

    async def execute(self, workflow_id: str, params: dict, output_validator, *, deadline=None):
        run_id = str(uuid4())
        args = [self.settings.runner_python, str(self.settings.script),
                "--workflow", workflow_id, "--params", json.dumps(params, allow_nan=False),
                "--run-id", run_id, "--contracts", str(self.settings.root / "contracts")]
        if self.settings.propagate_trace:
            for flag, value in (("--sentry-trace", sentry_sdk.get_traceparent()),
                                ("--baggage", sentry_sdk.get_baggage())):
                if value:
                    args.extend([flag, value])
        with sentry_sdk.start_span(op="runner.execute", name="runner.execute") as span:
            span.set_data("run_id", run_id)
            try:
                spawning = asyncio.create_task(asyncio.create_subprocess_exec(
                    *args, cwd=self.settings.root, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, start_new_session=True,
                ))
                try:
                    process = await asyncio.shield(spawning)
                except asyncio.CancelledError:
                    # Collect the handle even if cancellation lands between spawn and assignment.
                    try:
                        process = await asyncio.shield(spawning)
                    except OSError:
                        raise asyncio.CancelledError() from None
                    await asyncio.shield(stop_process(process))
                    raise
            except OSError as exc:
                raise BackendError("runner_unavailable", "The configured runner cannot be started") from exc
            try:
                timeout = self.settings.runner_timeout
                if deadline is not None:
                    timeout = min(timeout, max(0, deadline - asyncio.get_running_loop().time()))
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except (TimeoutError, asyncio.CancelledError) as exc:
                cleanup_timeout = 5 if deadline is None else min(5, max(
                    0.001, deadline + self.settings.cleanup_reserve - asyncio.get_running_loop().time()
                ))
                await asyncio.shield(stop_process(process, cleanup_timeout))
                if isinstance(exc, asyncio.CancelledError):
                    raise
                span.set_status("deadline_exceeded")
                return RunResult(run_id, error=BackendError("runner_timeout", "Runner exceeded its timeout"))
            span.set_data("exit_code", process.returncode)
            # Diagnostics belong to the trace, never the stdout JSON response.
            span.set_data("stderr", stderr.decode(errors="replace")[-4000:])
            for phase, milliseconds in parse_timings(stderr.decode(errors="replace")).items():
                span.set_data(f"runner.{phase}_ms", milliseconds)
            if process.returncode == 0:
                try:
                    data = json.loads(stdout, parse_constant=reject_constant)
                    if not isinstance(data, dict):
                        raise ValueError("Runner output must be one JSON object")
                    output_validator.validate(data)
                    span.set_status("ok")
                    return RunResult(run_id, data=data)
                except (ValueError, jsonschema.ValidationError):
                    error = BackendError("invalid_output", "Runner output did not match the workflow output schema")
            else:
                error = BackendError("runner_failed", "Runner exited with a failure")
            span.set_status("internal_error")
            artifact = self.settings.root / "runs" / run_id / "failure_payload.json"
            try:
                payload = read_json(artifact)
                self.failure_validator.validate(payload)
                failure = FailurePayload.model_validate(payload)
                if failure.workflow_id != workflow_id:
                    raise ValueError("Artifact belongs to another workflow")
                screenshot = Path(failure.screenshot_path)
                if not screenshot.is_absolute():
                    screenshot = self.settings.root / screenshot
                expected = artifact.parent / "failure.png"
                if screenshot.resolve() != expected.resolve() or not expected.is_file():
                    raise ValueError("Artifact screenshot does not belong to this run")
                return RunResult(run_id, failure=failure, error=error)
            except (OSError, ValueError, jsonschema.ValidationError):
                return RunResult(run_id, error=BackendError(
                    error.code, f"{error}. No valid failure artifact is available."
                ))
