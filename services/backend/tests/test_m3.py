"""M3 cooldown, finalized repair records, measurement ownership, and operator reset."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

import httpx

from services.backend.config import BackendError
from services.backend.main import create_app
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
        self.assertNotIn("cooldown_remaining_s", first)
        self.assertAlmostEqual(second["cooldown_remaining_s"], 12.0)  # stored at 1000, 15 s window, now 1003
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

    # Review fixes

    async def test_failure_at_the_navigation_step_does_not_start_a_recovery(self):
        payload = (await self.request(case="navigation")).json()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["code"], "runner_failed")
        self.assertIn("not a selector", payload["error"]["message"])
        self.assertFalse(payload["recovery_attempted"])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.recovery_files(), [])
        self.assertEqual(self.app.state.recovery.cooldown, {})

    def test_runner_python_defaults_to_the_project_venv_when_it_exists(self):
        from services.backend.config import default_runner_python
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(default_runner_python(root), sys.executable)
            (root / ".venv/bin").mkdir(parents=True)
            (root / ".venv/bin/python").write_text("")
            self.assertEqual(default_runner_python(root), str(root / ".venv/bin/python"))

    async def test_operator_endpoints_refuse_forwarded_requests(self):
        for path, method in (("/api/v1/status", "get"), ("/api/v1/admin/reset", "post")):
            plain = await getattr(self.client, method)(path)
            self.assertNotEqual(plain.status_code, 403, path)
            forwarded = await getattr(self.client, method)(path, headers={"X-Forwarded-For": "203.0.113.9"})
            self.assertEqual(forwarded.status_code, 403, path)

    async def test_a_logged_exception_still_reaches_sentry(self):
        """With log lines no longer becoming issues, log.exception sites must capture explicitly."""
        import sentry_sdk
        from sentry_sdk.transport import Transport
        envelopes = []

        class Memory(Transport):
            def capture_envelope(self, envelope):
                envelopes.append(envelope)
        from sentry_sdk.integrations.logging import LoggingIntegration
        # Same logging settings as production, where ERROR log lines do not become events by themselves.
        sentry_sdk.init(dsn="https://public@example.invalid/1", transport=Memory(), traces_sample_rate=0,
                        integrations=[LoggingIntegration(event_level=None)])
        self.addCleanup(sentry_sdk.init)
        with tempfile.TemporaryDirectory() as empty, patch("services.backend.main.sentry_sdk.init"):
            app = create_app(replace(self.settings, root=Path(empty)))  # no contract schemas: startup fails
            async with app.router.lifespan_context(app):
                self.assertIsNotNone(app.state.configuration_error)
        sentry_sdk.flush()
        events = [item.payload.json for envelope in envelopes for item in envelope.items if item.headers.get("type") == "event"]
        self.assertTrue(any("exception" in event for event in events), events)

    async def test_an_agent_that_gives_up_early_is_retried_within_the_cap(self):
        calls = []

        async def gives_up_once(settings, workflow, params, failed, **kwargs):
            calls.append(failed.failed_step)
            if len(calls) == 1:
                raise BackendError("agent_blocked", "Browser Use could not complete the task")
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = gives_up_once
        payload = (await self.request()).json()
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(calls, ["input_reference", "input_reference", "submit_button"])

    async def test_a_real_login_wall_spends_the_cap_and_fails_without_records(self):
        async def always_blocked(settings, workflow, params, failed, **kwargs):
            self.calls.append(failed.failed_step)
            raise BackendError("agent_blocked", "Browser Use could not complete the task")
        self.app.state.diagnose = always_blocked
        payload = (await self.request()).json()
        self.assertEqual((payload["status"], payload["error"]["code"]), ("failed", "agent_blocked"))
        self.assertEqual(len(self.calls), 3)
        self.assertNotIn("heal_records", payload)
        self.assertEqual(self.selectors(), self.baseline)

    async def test_recovery_summary_span_carries_flat_numbers_for_dashboards(self):
        """The numbers must be on a child span: Sentry does not index a transaction's own root span data."""
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.transport import Transport
        envelopes = []

        class Memory(Transport):
            def capture_envelope(self, envelope):
                envelopes.append(envelope)
        sentry_sdk.init(dsn="https://public@example.invalid/1", transport=Memory(), traces_sample_rate=1.0,
                        integrations=[LoggingIntegration(event_level=None)])
        self.addCleanup(sentry_sdk.init)
        self.app.state.diagnose = self.diagnose
        with patch("services.backend.main.sentry_sdk.init"):
            self.assertEqual((await self.request()).json()["status"], "healed")
        sentry_sdk.flush()
        transactions = [item.payload.json for envelope in envelopes for item in envelope.items
                        if item.headers.get("type") == "transaction"]
        spans = [span for transaction in transactions for span in transaction.get("spans", [])
                 if span.get("op") == "healer.summary"]
        self.assertEqual(len(spans), 1, [t.get("transaction") for t in transactions])
        data = spans[0]["data"]
        self.assertAlmostEqual(data["recovery.cost_usd"], 0.002)
        self.assertEqual((data["recovery.invocations"], data["recovery.total_tokens"], data["recovery.success"]), (2, 24, True))

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
