"""Free checks for paired benchmark accounting and sandbox evidence."""

from copy import deepcopy
from types import SimpleNamespace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.backend import bench_models as bench
from services.backend.config import BackendError
from services.backend.sandbox.records_site import SEEDS


def row(condition="candidate", *, ok=True, cost=0.007, complete=True, wall=15):
    return {"model": "test-model", "scenario": "sandbox-hard", "condition": condition, "ok": ok,
            "cost_usd": cost, "cost_complete": complete, "wall_s": wall,
            "total_tokens": 100, "quality": "attribute", "error": None}


def saved_state():
    return {"records": {**SEEDS, "bench-record": "bench-value", "canary-record": "canary-value"},
            "writes": 3, "supplier_note": None, "audit": [
                {"record_id": "canary-record", "new_value": "canary-value"},
                {"record_id": "bench-record", "new_value": "bench-value"},
                {"record_id": "bench-record", "new_value": "bench-value"}]}


class BenchmarkTests(unittest.TestCase):
    def test_pair_order_and_conservative_incomplete_costs(self):
        self.assertEqual(bench.paired_schedule(), [("baseline", 1), ("candidate", 1), ("candidate", 2),
                                                 ("baseline", 2), ("baseline", 3), ("candidate", 3)])
        self.assertEqual(bench.budget_cost(row()), 0.007)
        for cost in (None, 0.0, 0.002):
            self.assertEqual(bench.budget_cost(row(cost=cost, complete=False)), 0.15)
        self.assertEqual(bench.budget_cost(row(cost=0.2, complete=False)), 0.2)
        for cost in (float("nan"), float("inf"), -0.01, True):
            self.assertEqual(bench.budget_cost(row(cost=cost)), 0.15)
            self.assertIsNone(bench.summarize([row(cost=cost)])["mean_cost_usd"])

    def test_failed_trials_count_and_partial_costs_are_not_averaged(self):
        rows = [row(), row(ok=False, wall=30), row(cost=0.001, complete=False)]
        result = bench.summarize(rows)
        self.assertEqual((result["trials"], result["success"], result["mean_wall_s"]), (3, 2, 20))
        self.assertIsNone(result["mean_cost_usd"])
        self.assertIsNone(result["cost_per_success_usd"])

    def test_absolute_gates_and_informational_ratios(self):
        rows = [row("baseline", cost=0.003, wall=10) for _ in range(3)] + [row(cost=0.009, wall=19) for _ in range(3)]
        result = bench.comparison(rows)
        self.assertTrue(result["candidate_passed"])
        self.assertAlmostEqual(result["time_ratio"], 1.9)
        self.assertAlmostEqual(result["cost_ratio"], 3)
        for changes in ({"ok": False}, {"wall_s": 20.1}, {"cost_usd": 0.0101}, {"cost_complete": False}):
            changed = deepcopy(rows)
            for item in changed[3:]:
                item.update(changes)
            self.assertFalse(bench.comparison(changed)["candidate_passed"])
        self.assertFalse(bench.comparison(rows[:-1])["complete"])
        self.assertFalse(bench.comparison(rows[:-1])["candidate_passed"])

    def test_pre_followup_state_requires_price_only_audit_and_empty_note(self):
        initial, saved = {"records": SEEDS}, saved_state()
        self.assertTrue(all(bench.sandbox_checks(initial, saved, True).values()))
        for mutation in (lambda state: state.update(writes=4), lambda state: state["audit"].pop(),
                         lambda state: state.update(supplier_note={"note": "unexpected"}),
                         lambda state: state["audit"][0].update(record_id="SKU-1042"),
                         lambda state: state["records"].update({"SKU-1042": "changed"})):
            changed = deepcopy(saved)
            mutation(changed)
            self.assertFalse(all(bench.sandbox_checks(initial, changed, True).values()))
        legacy = {"records": saved["records"], "writes": 3}
        self.assertTrue(all(bench.sandbox_checks(initial, legacy, False).values()))
        self.assertFalse(all(bench.sandbox_checks(initial, legacy, True).values()))

    def test_trial_checks_three_writes_before_the_guarded_fourth_write(self):
        client = MagicMock()
        client.__enter__.return_value = client
        calls = []

        def post(*args, **kwargs):
            calls.append(kwargs["json"])
            if len(calls) == 1:
                payload = {"status": "healed", "data": bench.SANDBOX_PARAMS,
                           "heal_records": [{"verification_outcome": "committed"}]}
            else:
                self.assertIs(client.app.state.diagnose, bench.refuse_followup_diagnosis)
                payload = {"status": "success", "recovery_attempted": False}
                if followup_data is not None:
                    payload["data"] = followup_data
            return SimpleNamespace(json=lambda: payload)

        after = saved_state()
        after["writes"] = 4
        after["audit"].insert(0, {"record_id": "bench-record", "new_value": "bench-value"})

        def http(url, body=None):
            return states.pop(0) if url.endswith("/state") else {}

        client.post.side_effect = post
        for followup_data in (bench.SANDBOX_PARAMS, {"record_id": "wrong", "value": "wrong"}, None):
            with self.subTest(followup_data=followup_data):
                calls.clear()
                states = [{"records": SEEDS, "writes": 0}, saved_state(), deepcopy(after)]
                with patch.object(bench, "TestClient", return_value=client), patch.object(bench, "create_app"), patch.object(bench, "http", side_effect=http):
                    result = bench.trial("test-model", "sandbox-hard", "http://127.0.0.1:3100", "")
                self.assertEqual(result["ok"], followup_data == bench.SANDBOX_PARAMS, result)
                self.assertEqual(result["before_followup"]["writes"], 3)
                self.assertEqual(result["after_followup"]["writes"], 4)
                self.assertEqual(len(calls), 2)

    def test_trial_exception_is_retained_and_stops_further_paid_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "paired.json"
            args = ["bench_models", "--models", "test-model", "--scenario", "sandbox-hard",
                    "--baseline-site", str(bench.ROOT / "services/backend/sandbox/records_site.py"),
                    "--trials", "3", "--max-usd", "0.06", "--out", str(output)]
            with patch.object(bench.sys, "argv", args), patch.object(bench, "load_dotenv"), \
                    patch.object(bench.subprocess, "Popen"), patch.object(bench, "http"), \
                    patch.object(bench, "trial", side_effect=OSError("post-paid-state-unavailable")) as attempt:
                bench.main()
            saved = json.loads(output.read_text())
        attempt.assert_called_once()
        self.assertEqual(len(saved["rows"]), 1)
        self.assertEqual(saved["rows"][0]["error"], "trial_exception:OSError")
        self.assertEqual(saved["estimated_spend_usd"], 0.15)
        self.assertFalse(saved["comparison"]["complete"])
        self.assertFalse(saved["comparison"]["candidate_passed"])


class FollowupGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_followup_refuses_diagnosis(self):
        with self.assertRaises(BackendError) as failure:
            await bench.refuse_followup_diagnosis()
        self.assertEqual(failure.exception.code, "unexpected_recovery")
