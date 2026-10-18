"""M3 cooldown, finalized repair records, measurement ownership, and operator reset."""

import asyncio
import json
import os
import re
import subprocess
from unittest.mock import patch

import httpx

from services.backend.config import BackendError
from services.backend.runner import RunResult
from services.backend.tests.test_m1 import failure
from services.backend.tests.test_m2 import M2Harness


class M3Tests(M2Harness):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.now = 1000.0
        self.app.state.recovery.clock = lambda: self.now
        self.release = asyncio.Event()
        self.release.set()

        async def ambiguous(settings, workflow, params, failed, **kwargs):
            self.calls.append(failed.failed_step)
            raise BackendError("ambiguous_element", "Not unique")
        self.ambiguous = ambiguous
        self.app.state.diagnose = ambiguous

    def recovery_files(self):
        return list((self.settings.backend / "state").glob("recovery-*.json"))

    def outcomes(self, payload):
        return [(r["field"], r["verification_outcome"], r["version_before"], r.get("version_after"),
                 r.get("rollback_version")) for r in payload.get("heal_records", [])]

    def gated(self, diagnose):
        async def wrapper(settings, workflow, params, failed, **kwargs):
            await self.release.wait()
            return await diagnose(settings, workflow, params, failed, **kwargs)
        return wrapper

    def poison_submit(self):
        async def poisoned(settings, workflow, params, failed, **kwargs):
            candidate = await self.diagnose(settings, workflow, params, failed, **kwargs)
            candidate.duration_ms = 5
            if failed.failed_step == "submit_button":
                candidate.selector = 'button[data-action="poisoned"]'
            return candidate
        return poisoned

    # Cooldown

    async def test_cached_failure_starts_no_agent_and_writes_nothing(self):
        first = (await self.request("first")).json()
        before = self.selectors()
        self.now += 3
        second = (await self.request("second")).json()
        self.assertEqual(self.calls, ["input_reference"])
        self.assertEqual(self.selectors(), before)
        self.assertEqual(len(self.recovery_files()), 1)
        self.assertEqual(second["error"], first["error"])
        self.assertNotEqual(second["trace_id"], first["trace_id"])
        self.assert_failed(second)

    async def test_different_failed_step_during_cooldown_starts_a_fresh_recovery(self):
        self.assert_failed((await self.request()).json())
        self.path.write_text(json.dumps({**self.baseline, "fields": {**self.baseline["fields"], "input_reference": "#reference"}}))
        self.now += 1
        self.assert_failed((await self.request()).json())
        self.assertEqual(self.calls, ["input_reference", "submit_button"])

    async def test_changed_selector_map_or_evidence_misses_the_cache(self):
        await self.request()
        self.path.write_text(json.dumps({**self.baseline, "version": 7}))
        await self.request()
        self.assertEqual(self.calls, ["input_reference", "input_reference"])

    async def test_cache_hits_never_extend_expiry(self):
        await self.request()
        for offset in (10, 14.9):
            self.now = 1000 + offset
            await self.request()
            self.assertEqual(len(self.calls), 1)
        self.now = 1015.1
        await self.request()
        self.assertEqual(len(self.calls), 2)

    async def test_concurrent_requests_after_expiry_create_one_flight(self):
        await self.request()
        self.now = 1016
        self.release.clear()
        self.app.state.diagnose = self.gated(self.ambiguous)
        tasks = [asyncio.create_task(self.request(str(i))) for i in range(4)]
        await asyncio.sleep(0.1)
        self.release.set()
        for response in await asyncio.gather(*tasks):
            self.assert_failed(response.json())
        self.assertEqual(len(self.calls), 2)

    def test_cooldown_key_ignores_randomized_classes_from_real_portal_artifacts(self):
        from services.backend.recovery import cooldown_key
        snippet = ('<form id="permit-form"> <input id="permit-id"> <div id="chaos-modal" role="dialog">'
                   '<button class="legacy-action-%s" type="submit" data-action="submit">Submit Application</button></div></form>')
        first, second, moved = (failure("submit_button").model_copy(update={"dom_snippet": snippet % token})
                                for token in ("6rohw3mp", "k2x9qa1z", "x"))
        self.assertEqual(cooldown_key(first, self.baseline), cooldown_key(second, self.baseline))
        moved = moved.model_copy(update={"dom_snippet": moved.dom_snippet.replace("data-action", "data-other")})
        self.assertNotEqual(cooldown_key(first, self.baseline), cooldown_key(moved, self.baseline))

    async def test_failed_restoration_blocks_execution_and_is_not_cached(self):
        self.app.state.diagnose = self.poison_submit()
        with patch.object(self.app.state.store, "restore", side_effect=OSError("/secret/path unavailable")):
            payload = (await self.request()).json()
        self.assertEqual(payload["error"]["code"], "rollback_failed")
        self.assertNotIn("heal_records", payload)
        self.assertNotIn("/secret", json.dumps(payload))
        self.assertEqual((await self.request()).status_code, 503)
        self.assertEqual(self.app.state.recovery.cooldown, {})
        status = (await self.client.get("/api/v1/status")).json()
        self.assertIn("Rollback failed", status["blocked"])

    # Reset

    def git_commit_baseline(self):
        for command in (["init", "-q"], ["add", "contracts/selectors.json"],
                        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline"]):
            subprocess.run(["git", *command], cwd=self.root, check=True, capture_output=True)

    async def test_reset_restores_committed_selectors_and_clears_cooldown(self):
        self.git_commit_baseline()
        self.app.state.diagnose = self.diagnose
        self.assertEqual((await self.request()).json()["status"], "healed")
        self.assertNotEqual(self.selectors()["fields"], self.baseline["fields"])
        self.app.state.recovery.cooldown["sample-lookup"] = {"expires": 2000, "key": None, "outcome": None, "recovery_id": "x"}
        reply = await self.client.post("/api/v1/admin/reset")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 4)
        self.assertEqual(self.app.state.recovery.cooldown, {})

    async def test_reset_forgets_a_cached_failure(self):
        self.git_commit_baseline()
        await self.request()
        self.assertIn("sample-lookup", (await self.client.get("/api/v1/status")).json()["cooldown"])
        self.assertEqual((await self.client.post("/api/v1/admin/reset")).status_code, 200)
        await self.request()
        self.assertEqual(len(self.calls), 2)

    async def test_reset_refuses_active_recovery_and_remote_callers(self):
        self.release.clear()
        self.app.state.diagnose = self.gated(self.ambiguous)
        task = asyncio.create_task(self.request())
        await asyncio.sleep(0.1)
        self.assertEqual((await self.client.post("/api/v1/admin/reset")).status_code, 409)
        self.release.set()
        await task
        remote = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=("203.0.113.9", 1)),
                                   base_url="http://backend.test")
        self.addAsyncCleanup(remote.aclose)
        self.assertEqual((await remote.post("/api/v1/admin/reset")).status_code, 403)
        self.assertEqual((await remote.get("/api/v1/status")).status_code, 403)

    # Records

    async def test_canary_failure_marks_both_installed_records_rolled_back(self):
        self.app.state.diagnose = self.poison_submit()
        payload = (await self.request()).json()
        self.assertEqual(self.selectors()["version"], 4)
        self.assertEqual(self.outcomes(payload), [("input_reference", "rolled_back", 1, 2, 4),
                                                  ("submit_button", "rolled_back", 2, 3, 4)])
        self.assertNotIn("diff", payload)

    async def test_later_repair_failure_marks_first_patch_rolled_back(self):
        async def fail_later(settings, workflow, params, failed, **kwargs):
            if failed.failed_step == "submit_button":
                raise BackendError("agent_error", "Transient agent failure")
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = fail_later
        payload = (await self.request()).json()
        self.assertEqual(self.outcomes(payload), [("input_reference", "rolled_back", 1, 2, 3)])

    async def test_installed_and_rejected_candidates_keep_attempt_order(self):
        async def invalid(settings, workflow, params, failed, **kwargs):
            candidate = await self.diagnose(settings, workflow, params, failed, **kwargs)
            if failed.failed_step == "submit_button":
                candidate.selector = failed.expected_selector
            return candidate
        self.app.state.diagnose = invalid
        payload = (await self.request()).json()
        self.assertEqual(self.outcomes(payload), [("input_reference", "rolled_back", 1, 2, 3),
                                                  ("submit_button", "rejected", 2, None, None)])

    async def test_ambiguous_evidence_creates_no_record(self):
        payload = (await self.request()).json()
        self.assertNotIn("heal_records", payload)
        self.assertEqual(self.selectors(), self.baseline)

    # Measurements and waiters

    async def test_cost_and_duration_belong_only_to_the_request_that_ran_the_agent(self):
        async def measured(settings, workflow, params, failed, **kwargs):
            candidate = await self.diagnose(settings, workflow, params, failed, **kwargs)
            candidate.duration_ms = 5
            await self.release.wait()
            return candidate
        self.release.clear()
        self.app.state.diagnose = measured
        owner = asyncio.create_task(self.request("owner"))
        await asyncio.sleep(0.1)
        waiter = asyncio.create_task(self.request("waiter"))
        await asyncio.sleep(0.1)
        self.release.set()
        owner, waiter = [r.json() for r in await asyncio.gather(owner, waiter)]
        self.assertEqual((owner["agent_cost_usd"], owner["agent_duration_ms"]), (0.002, 10))
        for field in ("agent_cost_usd", "agent_duration_ms"):
            self.assertNotIn(field, waiter)
        self.assertEqual(owner["heal_records"], waiter["heal_records"])
        self.assertEqual(waiter["data"]["record_id"], "waiter")

    async def test_cache_hits_carry_original_records_but_no_measurements(self):
        self.app.state.diagnose = self.poison_submit()
        owner = (await self.request()).json()
        self.assertIn("agent_cost_usd", owner)
        hit = (await self.request()).json()
        self.assertEqual(hit["heal_records"], owner["heal_records"])
        for field in ("agent_cost_usd", "agent_duration_ms"):
            self.assertNotIn(field, hit)
        self.assertEqual(len(self.recovery_files()), 1)

    async def test_unknown_or_partial_measurements_are_omitted(self):
        calls = []
        async def retry(settings, workflow, params, failed, **kwargs):
            calls.append(failed.failed_step)
            if len(calls) == 1:
                raise BackendError("agent_timeout", "Timed out")
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = retry
        payload = (await self.request()).json()
        self.assertEqual(payload["status"], "healed")
        for field in ("agent_cost_usd", "agent_duration_ms"):
            self.assertNotIn(field, payload)

    async def test_waiter_replay_failure_keeps_committed_records_and_its_own_error(self):
        self.release.clear()
        self.app.state.diagnose = self.gated(self.diagnose)
        execute = self.app.state.runner.execute
        async def fail_waiter(workflow_id, params, output_validator, **kwargs):
            if params["record_id"] == "waiter":
                return RunResult("waiter", error=BackendError("runner_timeout", "Runner exceeded its timeout"))
            return await execute(workflow_id, params, output_validator, **kwargs)
        self.app.state.runner.execute = fail_waiter
        owner = asyncio.create_task(self.request("owner"))
        await asyncio.sleep(0.1)
        waiter = asyncio.create_task(self.request("waiter"))
        await asyncio.sleep(0.1)
        self.release.set()
        owner, waiter = [r.json() for r in await asyncio.gather(owner, waiter)]
        self.assertEqual(owner["status"], "healed")
        self.assertEqual(waiter["status"], "failed")
        self.assertEqual(waiter["error"]["code"], "runner_timeout")
        self.assertNotIn("diff", waiter)
        self.assertEqual(self.outcomes(waiter), self.outcomes(owner))
        self.assertTrue(all(r[1] == "committed" for r in self.outcomes(waiter)))

    # Safety

    async def test_error_messages_are_safe_to_show(self):
        unsafe = re.compile(r"/|\\|Traceback|File \"|secret-key|prompt|Authorization", re.I)
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "secret-key-123"}):
            scenarios = []
            scenarios.append((await self.request()).json())
            self.app.state.recovery.cooldown.clear()
            self.app.state.diagnose = self.poison_submit()
            scenarios.append((await self.request()).json())
            self.app.state.recovery.cooldown.clear()
            async with self.app.state.store.lock(exclusive=True):
                scenarios.append((await self.request()).json())
            self.app.state.recovery.cooldown.clear()
            with patch.object(self.app.state.store, "restore", side_effect=OSError("/etc/secret-key-123")):
                scenarios.append((await self.request()).json())
        codes = [payload["error"]["code"] for payload in scenarios]
        self.assertEqual(codes, ["ambiguous_element", "canary_failed", "lock_timeout", "rollback_failed"])
        for payload in scenarios:
            self.assertIsNone(unsafe.search(payload["error"]["message"]), payload["error"])

    async def test_responses_validate_against_the_shared_schema(self):
        from jsonschema import Draft202012Validator
        from services.backend.config import read_json
        check = Draft202012Validator(read_json(self.root / "contracts/workflow_execution_response.schema.json"))
        self.app.state.diagnose = self.poison_submit()
        for payload in ((await self.request()).json(), (await self.request()).json()):
            check.validate(payload)


if __name__ == "__main__":
    import unittest
    unittest.main()
