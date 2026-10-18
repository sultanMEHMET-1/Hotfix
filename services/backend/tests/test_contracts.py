"""Check the shared response boundary before any service depends on it."""

import copy
import json
from pathlib import Path
import unittest

import jsonschema
from pydantic import ValidationError

from contracts.api_types import FailurePayload, SelectorMap, WorkflowDefinition, WorkflowExecutionResponse


CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def load_json(path):
    return json.loads(path.read_text())


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(CONTRACTS / "workflow_execution_response.schema.json")
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def test_response_schema_matches_python_model(self):
        generated = WorkflowExecutionResponse.model_json_schema()
        expected = {k: v for k, v in self.schema.items() if k not in ("$schema", "$id")}
        self.assertEqual(generated, expected)

    def test_all_response_fixtures_validate(self):
        fixtures = list((CONTRACTS / "fixtures").glob("workflow_*.json"))
        self.assertEqual(len(fixtures), 4)
        for path in fixtures:
            with self.subTest(fixture=path.name):
                payload = load_json(path)
                self.validator.validate(payload)
                WorkflowExecutionResponse.model_validate(payload)

    def test_existing_selector_and_failure_fixtures_still_validate(self):
        for schema_name, data_path, model in (
            ("selectors.schema.json", "selectors/permit-application.json", SelectorMap),
            ("selectors.schema.json", "selectors/record-update.json", SelectorMap),
            ("failure_payload.schema.json", "fixtures/mock_failure.json", FailurePayload),
        ):
            with self.subTest(schema=schema_name):
                schema = load_json(CONTRACTS / schema_name)
                payload = load_json(CONTRACTS / data_path)
                jsonschema.Draft202012Validator(
                    schema, format_checker=jsonschema.FormatChecker()
                ).validate(payload)
                model.model_validate(payload)

    def test_workflow_schema_matches_python_model(self):
        schema = load_json(CONTRACTS / "workflow.schema.json")
        generated = WorkflowDefinition.model_json_schema()
        self.assertEqual(generated, {k: v for k, v in schema.items() if k not in ("$schema", "$id")})

    def test_every_workflow_definition_is_valid_and_has_a_matching_selector_map(self):
        schema = load_json(CONTRACTS / "workflow.schema.json")
        check = jsonschema.Draft202012Validator(schema)
        definitions = sorted((CONTRACTS / "workflows").glob("*.json"))
        self.assertGreaterEqual(len(definitions), 2)
        for path in definitions:
            with self.subTest(workflow=path.stem):
                payload = load_json(path)
                check.validate(payload)
                definition = WorkflowDefinition.model_validate(payload)
                selector_map = load_json(CONTRACTS / "selectors" / path.name)
                self.assertEqual(selector_map["workflow_id"], path.stem)
                fields = {step.field for step in definition.steps} | {o.field for o in definition.outputs.values()}
                self.assertLessEqual(fields, set(selector_map["fields"]))

    def test_definition_rules_reject_ambiguous_workflows(self):
        valid = load_json(CONTRACTS / "workflows/permit-application.json")
        mutations = [
            ("no canary", lambda d: d.pop("canary")),
            ("duplicate step field", lambda d: d["steps"].append(dict(d["steps"][0]))),
            ("field both step and output", lambda d: d["outputs"]["status"].update(field="submit_button")),
            ("input step without a param", lambda d: d["steps"][0].pop("param")),
            ("output missing from schema", lambda d: d["outputs"].pop("inspector")),
            ("non-string output", lambda d: d["output_schema"]["properties"]["status"].update(type="number")),
            ("bad read", lambda d: d["outputs"]["status"].update(read="html")),
            ("unknown action", lambda d: d["steps"][0].update(action_type="hover")),
        ]
        for label, mutate in mutations:
            with self.subTest(case=label):
                payload = copy.deepcopy(valid)
                mutate(payload)
                with self.assertRaises(ValidationError):
                    WorkflowDefinition.model_validate(payload)

    def test_legacy_response_and_unknown_metrics(self):
        payload = load_json(CONTRACTS / "fixtures/workflow_success.json")
        response = WorkflowExecutionResponse.model_validate(payload)
        self.assertFalse(response.recovery_attempted)
        self.assertEqual(response.heal_records, [])
        wire = response.model_dump(exclude_none=True)
        for field in ("agent_cost_usd", "agent_duration_ms", "cooldown_remaining_s", "error", "diff"):
            self.assertNotIn(field, wire)
        self.validator.validate(wire)

    def test_corrupt_responses_are_rejected_at_both_boundaries(self):
        valid = load_json(CONTRACTS / "fixtures/workflow_healed.json")
        mutations = [
            ("negative latency", lambda p: p.update(execution_time_ms=-1)),
            ("negative cost", lambda p: p.update(agent_cost_usd=-1)),
            ("negative duration", lambda p: p.update(agent_duration_ms=-1)),
            ("negative cooldown", lambda p: p.update(cooldown_remaining_s=-1)),
            ("extra field", lambda p: p.update(unapproved=True)),
            ("empty error", lambda p: p.update(error={"code": "", "message": ""})),
            ("invalid outcome", lambda p: p["heal_records"][0].update(verification_outcome="success")),
            ("invalid field", lambda p: p["heal_records"][0].update(field="not a field")),
            ("empty selector", lambda p: p["heal_records"][0]["diff"].update(new_selector="")),
            ("invalid version", lambda p: p["heal_records"][0].update(version_before=0)),
            ("missing evidence", lambda p: p["heal_records"][0].pop("evidence")),
            ("invalid history index", lambda p: p["heal_records"][0]["evidence"].update(history_step=-1)),
            ("extra evidence", lambda p: p["heal_records"][0]["evidence"].update(unapproved=True)),
        ]
        for label, mutate in mutations:
            with self.subTest(case=label):
                payload = copy.deepcopy(valid)
                mutate(payload)
                with self.assertRaises(jsonschema.ValidationError):
                    self.validator.validate(payload)
                with self.assertRaises(ValidationError):
                    WorkflowExecutionResponse.model_validate(payload)

    def test_nonfinite_metrics_do_not_serialize(self):
        valid = load_json(CONTRACTS / "fixtures/workflow_success.json")
        for field in ("execution_time_ms", "agent_cost_usd", "agent_duration_ms", "cooldown_remaining_s"):
            for value in (float("nan"), float("inf")):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        WorkflowExecutionResponse.model_validate({**valid, field: value})

    def test_transaction_examples_have_consistent_versions_and_summary(self):
        healed = load_json(CONTRACTS / "fixtures/workflow_healed.json")
        self.assertEqual(healed["diff"], healed["heal_records"][-1]["diff"])
        failed = load_json(CONTRACTS / "fixtures/workflow_rolled_back.json")
        self.assertNotIn("diff", failed)
        self.assertEqual(failed["data"], {})
        for record in failed["heal_records"]:
            self.assertEqual(record["verification_outcome"], "rolled_back")
            self.assertGreater(record["version_after"], record["version_before"])
            self.assertGreater(record["rollback_version"], record["version_after"])


if __name__ == "__main__":
    unittest.main()
