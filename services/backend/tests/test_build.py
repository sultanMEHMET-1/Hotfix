"""Verified first run and the bad-input guard, with the agent mocked."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

from services.backend import build
from services.backend.config import BackendError
from services.backend.runner import RunResult
from services.backend.tests.support import ROOT
from services.backend.tests.test_m1 import failure
from services.backend.tests.test_m2 import M2Harness


class BuildTests(M2Harness):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        patcher = patch.object(build, "BUILD_ON_FIRST_RUN", {"sample-lookup"})
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(build, "page_url", lambda settings, selectors, params: "http://portal.test/lookup")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.verify = AsyncMock(return_value=(0.004, 11000.0))
        patcher = patch.object(build, "verify", self.verify)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def fix_selectors(self):
        """The first request heals the broken selectors, which is not a build."""
        payload = (await self.request()).json()
        self.assertEqual(payload["status"], "healed")
        self.verify.assert_not_awaited()
        self.assertFalse(build.is_built(self.settings, "sample-lookup"))

    async def test_first_clean_run_is_verified_by_the_agent_then_later_runs_are_fast(self):
        await self.fix_selectors()
        first = (await self.request()).json()
        self.assertEqual(first["status"], "success")
        self.assertTrue(first["recovery_attempted"])
        self.assertEqual((first["agent_cost_usd"], first["agent_duration_ms"]), (0.004, 11000.0))
        self.assertEqual(first["data"]["record_id"], "request-123")
        self.verify.assert_awaited_once()
        self.assertTrue(build.is_built(self.settings, "sample-lookup"))
        second = (await self.request()).json()
        self.assertFalse(second["recovery_attempted"])
        self.assertNotIn("agent_cost_usd", second)
        self.verify.assert_awaited_once()

    async def test_a_disagreeing_agent_leaves_the_endpoint_unbuilt_and_returns_no_data(self):
        await self.fix_selectors()
        self.verify.side_effect = BackendError("build_mismatch", "different values")
        payload = (await self.request()).json()
        self.assert_failed(payload)
        self.assertEqual(payload["error"]["code"], "build_mismatch")
        self.assertFalse(build.is_built(self.settings, "sample-lookup"))

    async def test_clearing_the_marker_returns_the_endpoint_to_unbuilt(self):
        await self.fix_selectors()
        await self.request()
        self.assertTrue(build.is_built(self.settings, "sample-lookup"))
        build.clear(self.settings, "sample-lookup")
        self.assertFalse(build.is_built(self.settings, "sample-lookup"))

    async def test_workflows_outside_the_build_set_are_always_built(self):
        self.assertTrue(build.is_built(self.settings, "permit-application"))

    async def typo_fails_like_a_missing_element(self):
        """Only the typed input fails, at a selector step, the way a course that does not exist does."""
        original = self.app.state.runner.execute

        async def execute(workflow_id, params, validator, **kwargs):
            if params.get("record_id") == "typo":
                failed = failure("submit_button")
                return RunResult(run_id="typo", failure=failed.model_copy(update={"expected_selector": self.selectors()["fields"]["submit_button"]}))
            return await original(workflow_id, params, validator, **kwargs)
        self.app.state.runner.execute = execute

    async def test_a_failure_the_canary_does_not_reproduce_is_a_bad_input_and_costs_no_agent_run(self):
        await self.fix_selectors()
        await self.typo_fails_like_a_missing_element()
        calls_before = list(self.calls)
        payload = (await self.request("typo")).json()
        self.assert_failed(payload)
        self.assertEqual(payload["error"]["code"], "input_not_found")
        self.assertEqual(self.calls, calls_before)
        self.assertFalse(payload["recovery_attempted"])

    async def test_a_navigation_failure_is_not_blamed_on_the_input(self):
        await self.fix_selectors()
        payload = (await self.request(case="navigation")).json()
        self.assertEqual(payload["error"]["code"], "runner_failed")

    async def test_the_same_failure_with_broken_selectors_still_repairs(self):
        payload = (await self.request()).json()  # the canary fails too, so this is a real break
        self.assertEqual(payload["status"], "healed")


class SameTests(M2Harness):
    async def test_same_ignores_case_and_separators_but_not_content(self):
        self.assertTrue(build.same({"s": "Open\n218 of 240 Enrolled"}, {"s": "open 218 of 240 enrolled"}))
        self.assertFalse(build.same({"s": "Open\n218 of 240 Enrolled"}, {"s": "Closed 218 of 240 enrolled"}))
        self.assertTrue(build.same({"a": "x"}, {}))


class PageUrlTests(M2Harness):
    async def test_page_url_uses_the_real_runner_to_fill_the_target_url(self):
        settings = replace(self.settings, runner_script=ROOT / "services/runner/execute.py")
        selectors = {"target_url": "https://s.test/r?t={term}&subj={subject}&catlg={course_number:catalog}"}
        url = build.page_url(settings, selectors, {"term": "26F", "subject": "COM SCI", "course_number": "35l"})
        self.assertEqual(url, "https://s.test/r?t=26F&subj=COM+SCI&catlg=0035L")
