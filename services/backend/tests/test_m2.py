"""M2 transaction, lifetime, retry, and deadline checks without paid calls."""

import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from services.backend.config import BackendError, Settings
from services.backend.healer import Candidate
from services.backend.main import create_app
from services.backend.tests.support import make_root
from services.backend.tests.test_m1 import CORRECT, FIXTURES, failure, workflow_definition
from services.backend.healer import extract_evidence
from services.backend.config import Workflow


INPUT = 'input[data-testid="lookup-reference"]'


class M2Harness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.definition = workflow_definition()
        self.baseline = {"workflow_id": "sample-lookup", "version": 1, "target_url": "http://portal.test/lookup",
                         "fields": {"submit_button": "#broken", "input_reference": "#broken-input"}}
        self.path = make_root(self.root, "sample-lookup", self.definition, self.baseline)
        self.settings = Settings(root=self.root, runner_script=FIXTURES / "fake_runner.py", runner_timeout=1,
                                 recovery_timeout=3, cleanup_reserve=0.5, lock_timeout=0.1)
        self.env = patch.dict(os.environ, {"SENTRY_DSN": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = create_app(self.settings)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://backend.test")
        history = json.loads((FIXTURES / "recorded_history.json").read_text())
        self.evidence = {}
        for field in self.baseline["fields"]:
            _, self.evidence[field] = extract_evidence(history, Workflow.model_validate(self.definition), failure(field))
        self.calls = []

        async def diagnose(settings, workflow, params, failed, **kwargs):
            self.calls.append(failed.failed_step)
            return Candidate(INPUT if failed.failed_step == "input_reference" else CORRECT, self.evidence[failed.failed_step],
                             metrics={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
                                      "cached_prompt_tokens": 0, "cost_usd": 0.001})
        self.diagnose = diagnose
        self.app.state.diagnose = diagnose

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)

    def selectors(self):
        return json.loads(self.path.read_text())

    async def request(self, record_id="request-123", **params):
        return await self.client.post("/api/v1/run-workflow", json={"workflow": "sample-lookup", "params": {"record_id": record_id, **params}})

    def assert_failed(self, payload):
        self.assertEqual(payload["status"], "failed")
        self.assertFalse(payload["healed"])
        self.assertEqual(payload["data"], {})
        self.assertIn("error", payload)
        self.assertNotIn("diff", payload)

    def report(self):
        files = list((self.settings.backend / "state").glob("recovery-*.json"))
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text())


class M2Tests(M2Harness):
    async def test_two_fields_repair_in_order_without_reentrant_deadlock(self):
        acquisitions = []
        original = self.app.state.stores["sample-lookup"].lock
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def checked_lock(exclusive=False):
            acquisitions.append(exclusive)
            async with original(exclusive=exclusive):
                yield
        self.app.state.stores["sample-lookup"].lock = checked_lock
        payload = (await asyncio.wait_for(self.request(), 2)).json()
        self.assertEqual(payload["status"], "healed")
        self.assertEqual(self.calls, ["input_reference", "submit_button"])
        self.assertEqual(acquisitions, [False, True])
        self.assertEqual(self.selectors()["version"], 3)
        self.assertEqual(payload["diff"]["old_selector"], "#broken")
        self.assertEqual(self.report()["totals"]["total_tokens"], 24)
        self.assertNotIn("error", payload)
        self.assertEqual([(r["field"], r["verification_outcome"], r["version_before"], r["version_after"])
                          for r in payload["heal_records"]],
                         [("input_reference", "committed", 1, 2), ("submit_button", "committed", 2, 3)])
        self.assertEqual(payload["agent_cost_usd"], 0.002)
        self.assertNotIn("agent_duration_ms", payload)  # Mocked candidates report no SDK duration.

    async def test_canary_failure_restores_both_patches_with_higher_version(self):
        async def poisoned(settings, workflow, params, failed, **kwargs):
            candidate = await self.diagnose(settings, workflow, params, failed, **kwargs)
            if failed.failed_step == "submit_button":
                candidate.selector = 'button[data-action="poisoned"]'
            return candidate
        self.app.state.diagnose = poisoned
        self.assert_failed((await self.request()).json())
        self.assertEqual(self.calls, ["input_reference", "submit_button"])
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 4)
        self.assertEqual(self.report()["error_code"], "canary_failed")

    async def test_later_repair_failure_restores_first_patch(self):
        async def fail_later(settings, workflow, params, failed, **kwargs):
            if failed.failed_step == "submit_button":
                raise BackendError("agent_error", "Transient agent failure")
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = fail_later
        self.assert_failed((await self.request()).json())
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 3)
        self.assertEqual(len(self.report()["attempts"]), 3)
        self.assertEqual(self.report()["error_code"], "agent_error")

    async def test_deadline_during_agent_restores_first_patch(self):
        self.settings.recovery_timeout = 0.4
        self.settings.cleanup_reserve = 0.15
        async def stall_later(settings, workflow, params, failed, **kwargs):
            if failed.failed_step == "submit_button":
                await asyncio.sleep(10)
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = stall_later
        started = asyncio.get_running_loop().time()
        self.assert_failed((await asyncio.wait_for(self.request(), 1)).json())
        self.assertLess(asyncio.get_running_loop().time() - started, 0.8)
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 3)
        self.assertEqual(self.report()["error_code"], "recovery_timeout")

    async def test_request_cancellation_after_first_patch_preserves_background_and_waiter(self):
        patched = asyncio.Event()
        release = asyncio.Event()
        execute = self.app.state.runner.execute
        executions = []

        async def pause(workflow_id, params, output_validator, **kwargs):
            executions.append(params["record_id"])
            if len(executions) == 2:
                patched.set()
                await release.wait()
            return await execute(workflow_id, params, output_validator, **kwargs)
        self.app.state.runner.execute = pause
        owner = asyncio.create_task(self.request("owner"))
        waiter = None
        try:
            await asyncio.wait_for(patched.wait(), 1)
            self.assertEqual(self.selectors()["version"], 2)
            shared = self.app.state.recovery.active("sample-lookup")
            owner.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await owner
            self.assertFalse(shared.cancelled())
            waiter = asyncio.create_task(self.request("waiter"))
            await asyncio.sleep(0.02)
            release.set()
            payload = (await asyncio.wait_for(waiter, 2)).json()
            self.assertEqual(payload["status"], "healed")
            self.assertEqual(payload["data"]["record_id"], "waiter")
            self.assertEqual(self.calls, ["input_reference", "submit_button"])
            self.assertEqual(self.selectors()["version"], 3)
            self.assertEqual(len(self.report()["attempts"]), 2)
        finally:
            release.set()
            await asyncio.gather(owner, *([waiter] if waiter else []), return_exceptions=True)

    async def test_transient_agent_timeout_retries_same_field_within_three_invocations(self):
        calls = []
        async def retry(settings, workflow, params, failed, **kwargs):
            calls.append(failed.failed_step)
            if len(calls) == 1:
                raise BackendError("agent_timeout", "Timed out")
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = retry
        self.assertEqual((await self.request()).json()["status"], "healed")
        self.assertEqual(calls, ["input_reference", "input_reference", "submit_button"])
        self.assertFalse(self.report()["totals"]["total_tokens_complete"])

    async def test_ambiguous_evidence_aborts_without_retry(self):
        async def ambiguous(*args, **kwargs):
            self.calls.append("ambiguous")
            raise BackendError("ambiguous_element", "Not unique")
        self.app.state.diagnose = ambiguous
        self.assert_failed((await self.request()).json())
        self.assertEqual(self.calls, ["ambiguous"])
        self.assertEqual(self.selectors(), self.baseline)

    async def test_same_step_failure_rolls_back_without_retry(self):
        async def wrong(settings, workflow, params, failed, **kwargs):
            candidate = await self.diagnose(settings, workflow, params, failed, **kwargs)
            candidate.selector = "#still-broken"
            return candidate
        self.app.state.diagnose = wrong
        self.assert_failed((await self.request()).json())
        self.assertEqual(self.calls, ["input_reference"])
        self.assertEqual(self.selectors()["version"], 3)

    async def test_three_agent_failures_never_invoke_a_fourth(self):
        async def unavailable(*args, **kwargs):
            self.calls.append("failed")
            raise BackendError("agent_error", "Transient failure")
        self.app.state.diagnose = unavailable
        self.assert_failed((await self.request()).json())
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.selectors(), self.baseline)

    async def test_no_result_retries_same_field(self):
        invocations = []
        async def no_result(settings, workflow, params, failed, **kwargs):
            invocations.append(failed.failed_step)
            if len(invocations) == 1:
                return None
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = no_result
        self.assertEqual((await self.request()).json()["status"], "healed")
        self.assertEqual(invocations, ["input_reference", "input_reference", "submit_button"])

    async def test_recovery_lock_wait_uses_same_deadline(self):
        self.settings.recovery_timeout = 0.15
        self.settings.cleanup_reserve = 0.05
        execute = self.app.state.runner.execute
        output_validator = self.app.state.workflows["sample-lookup"][2]
        result = await execute("sample-lookup", {"record_id": "owner"}, output_validator)
        workflow = self.app.state.workflows["sample-lookup"][0]
        async with self.app.state.stores["sample-lookup"].lock(exclusive=True):
            task = self.app.state.recovery.start("sample-lookup", workflow, {"record_id": "owner"}, output_validator,
                                                 self.baseline, result)
            outcome = await asyncio.wait_for(asyncio.shield(task), 0.5)
            self.assertEqual(outcome.error.code, "recovery_timeout")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.selectors(), self.baseline)

    async def test_cancellation_during_runner_spawn_collects_and_kills_process(self):
        spawned = asyncio.Event()
        release = asyncio.Event()
        processes = []
        original = asyncio.create_subprocess_exec
        async def delayed_spawn(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            spawned.set()
            await release.wait()
            return process
        validator = self.app.state.workflows["sample-lookup"][2]
        with patch("services.backend.runner.asyncio.create_subprocess_exec", side_effect=delayed_spawn):
            run = asyncio.create_task(self.app.state.runner.execute("sample-lookup", {"record_id": "x", "case": "hang"}, validator))
            try:
                await asyncio.wait_for(spawned.wait(), 1)
                run.cancel()
                await asyncio.sleep(0)
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(run, 1)
                self.assertIsNotNone(processes[0].returncode)
                with self.assertRaises(ProcessLookupError):
                    os.kill(processes[0].pid, 0)
            finally:
                release.set()
                await asyncio.gather(run, return_exceptions=True)

    async def test_failed_flight_is_shared_then_served_from_cooldown(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        async def ambiguous(*args, **kwargs):
            self.calls.append("ambiguous")
            entered.set()
            await release.wait()
            raise BackendError("ambiguous_element", "Not unique")
        self.app.state.diagnose = ambiguous
        owner = asyncio.create_task(self.request("owner"))
        waiter = None
        try:
            await asyncio.wait_for(entered.wait(), 1)
            waiter = asyncio.create_task(self.request("waiter"))
            await asyncio.sleep(0.02)
            release.set()
            for response in await asyncio.gather(owner, waiter):
                self.assert_failed(response.json())
            self.assertEqual(self.calls, ["ambiguous"])
            # The failed flight now sits in the 15 s cooldown; see test_m3 for its full behavior.
            self.assert_failed((await self.request("later")).json())
            self.assertEqual(self.calls, ["ambiguous"])
        finally:
            release.set()
            await asyncio.gather(owner, *([waiter] if waiter else []), return_exceptions=True)

    async def test_schema_invalid_replay_restores_all_patches(self):
        self.assert_failed((await self.request(case="invalid-replay")).json())
        self.assertEqual(self.calls, ["input_reference", "submit_button"])
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 4)
        self.assertEqual(self.report()["error_code"], "invalid_output")

    async def test_invalid_candidate_after_partial_progress_aborts_without_retry(self):
        async def invalid(settings, workflow, params, failed, **kwargs):
            candidate = await self.diagnose(settings, workflow, params, failed, **kwargs)
            if failed.failed_step == "submit_button":
                candidate.selector = failed.expected_selector
            return candidate
        self.app.state.diagnose = invalid
        self.assert_failed((await self.request()).json())
        self.assertEqual(self.calls, ["input_reference", "submit_button"])
        self.assertEqual(self.selectors()["version"], 3)
        self.assertEqual(self.report()["error_code"], "invalid_candidate")

    async def test_no_unique_css_after_first_patch_aborts_and_rolls_back(self):
        async def unresolved(settings, workflow, params, failed, **kwargs):
            if failed.failed_step == "submit_button":
                self.calls.append(failed.failed_step)
                raise BackendError("unresolved_element", "No unique CSS matches the live target")
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = unresolved
        self.assert_failed((await self.request()).json())
        self.assertEqual(self.calls, ["input_reference", "submit_button"])
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 3)
        self.assertEqual(self.report()["error_code"], "unresolved_element")

    async def test_fast_path_lock_wait_is_bounded_without_starting_agent(self):
        async with self.app.state.stores["sample-lookup"].lock(exclusive=True):
            self.assert_failed((await asyncio.wait_for(self.request(), 0.5)).json())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.selectors(), self.baseline)

    async def test_missing_demo_canary_rejected_at_startup(self):
        definition = copy.deepcopy(self.definition)
        definition.pop("canary")
        (self.root / "contracts/workflows/sample-lookup.json").write_text(json.dumps(definition))
        app = create_app(self.settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://backend.test") as client:
                response = await client.post("/api/v1/run-workflow", json={"workflow": "sample-lookup", "params": {"record_id": "x"}})
                self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
