"""Read healing refusals and rules that need no browser and no model."""

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from contracts.api_types import WorkflowDefinition
from services.backend.config import BackendError, Settings
from services.backend.healer import diagnose, read_candidate
from services.backend.recovery import reads_match, validate_failure
from services.backend.tests.test_m1 import failure

ROOT = Path(__file__).resolve().parents[3]
PERMIT = WorkflowDefinition.model_validate(json.loads((ROOT / "contracts/workflows/permit-application.json").read_text()))


def fake_browser(found):
    async def evaluate(params, session_id):
        return {"result": {"value": found}}

    async def session():
        return SimpleNamespace(session_id="s", cdp_client=SimpleNamespace(
            send=SimpleNamespace(Runtime=SimpleNamespace(evaluate=evaluate))))
    return SimpleNamespace(get_or_create_cdp_session=session)


def fake_history(**values):
    structured = SimpleNamespace(**values) if values else None
    return SimpleNamespace(structured_output=structured, total_duration_seconds=lambda: 2.0)


def unique(selector='span[data-testid="status"]'):
    return {"count": 1, "selector": selector, "tag": "SPAN", "attributes": {"data-testid": "status"}}


SERIALIZED = {"history": [{}, {}, {}]}


class ReadCandidateTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, found, history=None, failed=None):
        failed = failed or failure("status_badge").model_copy(update={"expected_selector": "#old-badge"})
        return await read_candidate(fake_browser(found), history or fake_history(status="Approved"), SERIALIZED,
                                    failed, ["status"], {"cost_usd": 0.01})

    async def test_a_unique_element_becomes_a_read_candidate_with_evidence(self):
        candidate = await self.call(unique(), fake_history(status="  Approved \n"))
        self.assertEqual(candidate.selector, 'span[data-testid="status"]')
        self.assertEqual(candidate.reported, {"status": "Approved"})  # whitespace collapsed
        self.assertEqual((candidate.evidence.action_type, candidate.evidence.history_step, candidate.evidence.node_name),
                         ("read", 2, "SPAN"))
        self.assertEqual(candidate.cost_usd, 0.01)

    async def test_refusals(self):
        cases = [
            ("no report", unique(), fake_history(), "agent_no_result"),
            ("blank report", unique(), fake_history(status="   "), "agent_no_result"),
            ("no element shows it", {"count": 0}, None, "ambiguous_element"),
            ("two elements show it", {"count": 2}, None, "ambiguous_element"),
            ("unchanged selector", unique("#old-badge"), None, "unresolved_element"),
            ("selector embeds the value", unique('span[data-testid="Approved"]'), None, "unresolved_element"),
            ("no derivable selector", {"count": 1, "selector": None, "tag": "SPAN", "attributes": {}}, None, "unresolved_element"),
        ]
        for label, found, history, code in cases:
            with self.subTest(case=label):
                with self.assertRaises(BackendError) as caught:
                    await self.call(found, history)
                self.assertEqual(caught.exception.code, code)


class ReadPositionTests(unittest.TestCase):
    def selectors(self, workflow="permit-application"):
        return {"workflow_id": workflow, "version": 1, "target_url": "http://portal.test/x",
                "fields": {"input_permit_id": "#a", "input_applicant_name": "#b", "submit_button": "#c", "status_badge": "#old-badge"}}

    def result(self, step, selector):
        update = {"workflow_id": "permit-application", "failed_step": step, "expected_selector": selector}
        return SimpleNamespace(failure=failure().model_copy(update=update), error=None)

    def test_replay_values_match_the_reported_ones_ignoring_whitespace_only(self):
        self.assertTrue(reads_match({"status": "Approved\nby  Davis"}, {"status": "Approved by Davis"}))
        self.assertFalse(reads_match({"status": "Approved by Smith"}, {"status": "Approved by Davis"}))
        self.assertFalse(reads_match({}, {"status": "Approved"}))

    def test_reads_come_after_every_step(self):
        steps = [validate_failure("permit-application", PERMIT, self.selectors(), self.result(name, selector))
                 for name, selector in (("input_permit_id", "#a"), ("submit_button", "#c"), ("status_badge", "#old-badge"))]
        self.assertEqual(steps, [0, 2, 3])  # a fixed click means the next failure at the read is forward progress

    def test_an_unknown_field_is_still_unmapped(self):
        selectors = {**self.selectors(), "fields": {**self.selectors()["fields"], "mystery": "#m"}}
        with self.assertRaises(BackendError) as caught:
            validate_failure("permit-application", PERMIT, selectors, self.result("mystery", "#m"))
        self.assertEqual(caught.exception.code, "unmapped_step")


class AttributeOnlyReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_read_with_only_attribute_outputs_is_refused_before_any_browser_starts(self):
        definition = copy.deepcopy(PERMIT.model_dump())
        definition["outputs"] = {"status": {"field": "status_badge", "read": "attr:data-status"},
                                 "inspector": {"field": "status_badge", "read": "attr:data-inspector"},
                                 "permit_id": {"field": "status_badge", "read": "attr:data-permit"}}
        workflow = WorkflowDefinition.model_validate(definition)
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "k", "GEMINI_MODEL": "m"}), patch(
                "services.backend.healer.load_browser_use", side_effect=AssertionError("a browser must not start")):
            with self.assertRaises(BackendError) as caught:
                await diagnose(Settings(root=ROOT), workflow, {}, failure("status_badge"))
        self.assertEqual(caught.exception.code, "ambiguous_element")


if __name__ == "__main__":
    unittest.main()
