"""M1 acceptance and adversarial checks, with no model or Sentry network calls."""

import asyncio
from concurrent.futures import CancelledError as FutureCancelledError, ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import sentry_sdk
from sentry_sdk.transport import Transport

from contracts.api_types import FailurePayload
from services.backend.config import BackendError, Settings, Workflow, masked_output
from services.backend.healer import Candidate, extract_evidence
from services.backend.main import create_app


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"
CORRECT = 'button[data-action="lookup"]'


def workflow_definition():
    return {
        "goal": "Look up the record reference and return its status.",
        "steps": [
            {"field": "input_reference", "action_type": "input", "role": "textbox", "label": "Record reference"},
            {"field": "submit_button", "action_type": "click", "role": "button", "label": "Look up record"},
        ],
        "params_schema": {"type": "object", "required": ["record_id"], "additionalProperties": False,
                          "properties": {"record_id": {"type": "string"}, "case": {"type": "string"}}},
        "output_schema": {"type": "object", "required": ["record_id", "status"], "additionalProperties": False,
                          "properties": {"record_id": {"type": "string"}, "status": {"const": "found"}}},
        "canary": {"params": {"record_id": "canary"}, "expected_output": {"record_id": "canary", "status": "found"}},
    }


def failure(field="submit_button"):
    return FailurePayload(
        workflow_id="sample-lookup", timestamp=1, failed_step=field,
        expected_selector="#broken", page_url="http://portal.test/lookup",
        dom_snippet='<button data-action="lookup">Look up record</button>',
        screenshot_path="runs/test/failure.png", error_message="Missing selector",
    )


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.history = json.loads((FIXTURES / "recorded_history.json").read_text())
        self.workflow = Workflow.model_validate(workflow_definition())

    def test_recorded_input_and_button_map_to_executed_results(self):
        for field, node in (("input_reference", "INPUT"), ("submit_button", "BUTTON")):
            with self.subTest(field=field):
                element, evidence = extract_evidence(self.history, self.workflow, failure(field))
                self.assertEqual(element["node_name"], node)
                self.assertEqual(evidence.node_name, node)
                self.assertIn("Unique executed", evidence.reasoning)

    def test_ambiguous_failed_and_unexecuted_actions_are_rejected(self):
        for kind in ("duplicate", "error", "missing_result", "missing_element", "wrong_order"):
            history = copy.deepcopy(self.history)
            step = history["history"][2]
            if kind == "duplicate":
                history["history"].append(copy.deepcopy(step))
            elif kind == "error":
                step["result"][0]["error"] = "Click failed"
            elif kind == "missing_result":
                step["result"] = []
            elif kind == "missing_element":
                step["state"]["interacted_element"] = []
            else:
                history["history"][1], history["history"][2] = step, history["history"][1]
            with self.subTest(kind=kind), self.assertRaises(BackendError):
                extract_evidence(history, self.workflow, failure())

    def test_canary_exclusions_cannot_remove_all_meaning(self):
        self.assertEqual(masked_output({"status": "found", "time": 1}, ["/time"]), {"status": "found"})
        for data, paths in (({"time": 1}, ["/time"]), ({"nested": {"time": 1}}, ["/nested/time"]), ({"x": 1}, [""])):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                masked_output(data, paths)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_mocked_agent_history_is_grounded_and_browser_is_cleaned(self):
        await self.exercise_adapter("success")

    async def test_agent_timeout_always_cleans_browser(self):
        await self.exercise_adapter("timeout")

    async def test_ambiguous_agent_history_is_rejected_and_cleaned(self):
        await self.exercise_adapter("ambiguous")

    async def test_no_unique_live_css_fails_explicitly_and_cleans_browser(self):
        await self.exercise_adapter("unresolved")

    async def test_no_agent_result_is_retryable_and_clients_are_cleaned(self):
        await self.exercise_adapter("no_result")

    async def exercise_adapter(self, mode):
        from services.backend.healer import diagnose
        history = json.loads((FIXTURES / "recorded_history.json").read_text())
        if mode == "ambiguous":
            history["history"].append(copy.deepcopy(history["history"][2]))
        closed = []
        clients_closed = []
        class Browser:
            def __init__(self, **kwargs):
                pass
            async def get_or_create_cdp_session(self):
                async def evaluate(params, session_id):
                    selector = None if mode == "unresolved" else CORRECT if 'html/body/button' in params["expression"] else 'input[data-testid="lookup-reference"]'
                    return {"result": {"value": selector}}
                return SimpleNamespace(cdp_client=SimpleNamespace(send=SimpleNamespace(
                    Runtime=SimpleNamespace(evaluate=evaluate))), session_id="test")
            async def kill(self):
                closed.append(True)
        class Chat:
            def __init__(self, **kwargs):
                async def aclose():
                    clients_closed.append("async")
                self._client = SimpleNamespace(aio=SimpleNamespace(aclose=aclose), close=lambda: clients_closed.append("sync"))
            async def ainvoke(self):
                return None
        class Element:
            @staticmethod
            def load_from_enhanced_dom_tree(node):
                return SimpleNamespace(to_dict=lambda: node)
        class Agent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
            async def run(self, max_steps):
                if mode == "no_result":
                    return None
                if mode == "timeout":
                    await asyncio.sleep(30)
                await self.kwargs["llm"].ainvoke()
                for step in history["history"]:
                    actions = step["model_output"]["action"]
                    elements = step["state"]["interacted_element"]
                    for action, element in zip(actions, elements):
                        if not element:
                            continue
                        action_params = next(iter(action.values()))
                        index = action_params["index"]
                        state = SimpleNamespace(dom_state=SimpleNamespace(selector_map={index: element}))
                        output = SimpleNamespace(action=[SimpleNamespace(get_index=lambda index=index: index)])
                        await self.kwargs["register_new_step_callback"](state, output, 0)
                return SimpleNamespace(model_dump=lambda: history, total_duration_seconds=lambda: 1,
                                       usage=SimpleNamespace(entry_count=1, total_cost=0.002))
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(root=Path(directory), agent_timeout=0.05 if mode == "timeout" else 2)
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key-not-sent", "GEMINI_MODEL": "test-model"}), patch(
                "services.backend.healer.load_browser_use", return_value=(Agent, Browser, Chat, Element)
            ):
                if mode == "success":
                    candidate = await diagnose(settings, Workflow.model_validate(workflow_definition()), {"record_id": "x"}, failure())
                    self.assertEqual(candidate.selector, CORRECT)
                    self.assertEqual(candidate.cost_usd, 0.002)
                    self.assertEqual(candidate.duration_ms, 1000)
                else:
                    with self.assertRaises(BackendError) as caught:
                        await diagnose(settings, Workflow.model_validate(workflow_definition()), {"record_id": "x"}, failure())
                    expected = {"timeout": "agent_timeout", "unresolved": "unresolved_element", "no_result": "agent_no_result"}
                    self.assertEqual(caught.exception.code, expected.get(mode, "ambiguous_element"))
        self.assertEqual(closed, [True])
        self.assertEqual(clients_closed, ["async", "sync"])

    async def test_failed_sdk_cleanup_force_kills_its_owned_process(self):
        from services.backend.healer import close_browser
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: process.poll() is None and process.kill())
        async def broken_kill():
            raise RuntimeError("SDK cleanup failed")
        browser = SimpleNamespace(kill=broken_kill,
                                  _local_browser_watchdog=SimpleNamespace(browser_pid=process.pid))
        with self.assertRaises(BackendError):
            await close_browser(browser)
        self.assertIsNotNone(process.poll())


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "contracts", self.root / "contracts")
        self.backend = self.root / "services/backend"
        (self.backend / "workflows").mkdir(parents=True)
        self.definition = workflow_definition()
        (self.backend / "workflows/sample-lookup.json").write_text(json.dumps(self.definition))
        self.baseline = {"workflow_id": "sample-lookup", "target_url": "http://portal.test/lookup",
                         "version": 1, "fields": {"input_reference": "#reference", "submit_button": "#broken"}}
        self.write_selectors(self.baseline)
        self.settings = Settings(root=self.root, runner_script=FIXTURES / "fake_runner.py", runner_timeout=2)
        self.app = create_app(self.settings)
        self.env = patch.dict(os.environ, {"SENTRY_DSN": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.calls = 0
        history = json.loads((FIXTURES / "recorded_history.json").read_text())
        _, self.evidence = extract_evidence(history, Workflow.model_validate(self.definition), failure())
        self.new_selector = CORRECT

        async def diagnose(*args, **kwargs):
            self.calls += 1
            return Candidate(self.new_selector, self.evidence)
        self.app.state.diagnose = diagnose

    def write_selectors(self, value):
        (self.root / "contracts/selectors.json").write_text(json.dumps(value))

    def selectors(self):
        return json.loads((self.root / "contracts/selectors.json").read_text())

    def recovery_error(self):
        report = next((self.backend / "state").glob("recovery-*.json"))
        return json.loads(report.read_text())["error_code"]

    def request(self, **params):
        return self.client.post("/api/v1/run-workflow", json={"workflow": "sample-lookup", "params": {"record_id": "request-123", **params}})

    def test_fast_success_never_invokes_healer(self):
        self.write_selectors({**self.baseline, "fields": {**self.baseline["fields"], "submit_button": CORRECT}})
        with patch("services.backend.healer.load_browser_use", side_effect=AssertionError("Browser Use imported")):
            response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(self.calls, 0)
        self.assertEqual(response.json()["data"]["record_id"], "request-123")

    def test_one_broken_field_commits_only_after_replay_and_canary(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "healed")
        self.assertTrue(payload["healed"])
        self.assertTrue(payload["recovery_attempted"])
        self.assertEqual(payload["diff"]["new_selector"], CORRECT)
        self.assertEqual(self.selectors()["version"], 2)
        self.assertEqual(self.calls, 1)
        self.assertEqual(len(list((self.root / "runs").iterdir())), 1)  # Only failure runs create artifacts.
        self.assertEqual(len(list((self.backend / "state").glob("baseline-*.json"))), 1)
        self.assertEqual(len(payload["trace_id"]), 32)

    def test_wrong_selector_rolls_back_as_a_higher_version(self):
        self.new_selector = 'button[data-action="wrong"]'
        payload = self.request().json()
        self.assertEqual(payload["status"], "failed")
        self.assertFalse(payload["healed"])
        self.assertNotIn("diff", payload)
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 3)
        self.assertEqual(self.calls, 1)

    def test_schema_valid_wrong_data_fails_canary(self):
        self.new_selector = 'button[data-action="poisoned"]'
        payload = self.request().json()
        self.assertEqual(payload["status"], "failed")
        self.assertNotIn("error", payload)
        self.assertEqual(self.recovery_error(), "canary_failed")
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 3)

    def test_agent_failure_leaves_baseline_untouched(self):
        async def timeout(*args, **kwargs):
            raise BackendError("agent_timeout", "Timed out")
        self.app.state.diagnose = timeout
        payload = self.request().json()
        self.assertEqual(payload["status"], "failed")
        self.assertNotIn("error", payload)
        self.assertEqual(self.recovery_error(), "agent_timeout")
        self.assertEqual(self.selectors(), self.baseline)

    def test_malformed_and_foreign_artifacts_do_not_engage_agent(self):
        for case in ("missing", "foreign", "junk"):
            with self.subTest(case=case):
                payload = self.request(case=case).json()
                self.assertEqual(payload["status"], "failed")
                self.assertEqual(self.calls, 0)
                self.assertEqual(self.selectors(), self.baseline)

    def test_runner_timeout_kills_process(self):
        self.settings.runner_timeout = 0.2
        payload = self.request(case="hang").json()
        self.assertEqual(payload["status"], "failed")
        self.assertNotIn("error", payload)
        pid = int((self.root / "runner.pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_request_validation_and_unknown_workflow(self):
        self.assertEqual(self.client.post("/api/v1/run-workflow", json={"workflow": "sample-lookup", "params": {}}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/run-workflow", json={"workflow": "../escape", "params": {}}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/run-workflow", json={"workflow": "unknown", "params": {}}).status_code, 404)
        self.assertEqual(self.calls, 0)

    def test_cancellation_during_verification_restores_baseline(self):
        original = self.app.state.runner.execute
        calls = 0
        async def cancelled(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise asyncio.CancelledError()
            return await original(*args, **kwargs)
        self.app.state.runner.execute = cancelled
        try:
            self.request()
        except (asyncio.CancelledError, FutureCancelledError):
            pass
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 3)

    def test_overlapping_requests_cannot_consume_a_provisional_map(self):
        async def delayed(*args, **kwargs):
            self.calls += 1
            await asyncio.sleep(0.15)
            return Candidate(CORRECT, self.evidence)
        self.app.state.diagnose = delayed
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.request().json(), range(2)))
        self.assertTrue(all(response["status"] in ("success", "healed") for response in responses))
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.selectors()["version"], 2)

    def test_canary_timeout_rolls_back(self):
        execute = self.app.state.runner.execute
        calls = 0
        async def timeout(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                from services.backend.runner import RunResult
                return RunResult("canary", error=BackendError("runner_timeout", "Timed out"))
            return await execute(*args, **kwargs)
        self.app.state.runner.execute = timeout
        payload = self.request().json()
        self.assertEqual(payload["status"], "failed")
        self.assertNotIn("error", payload)
        self.assertEqual(self.recovery_error(), "canary_failed")
        self.assertEqual(self.selectors()["version"], 3)
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])

    def test_sentry_fingerprint_spans_and_trace_correlation(self):
        envelopes = []
        class MemoryTransport(Transport):
            def capture_envelope(self, envelope):
                envelopes.append(envelope)
        sentry_sdk.init(dsn="https://public@example.invalid/1", transport=MemoryTransport(),
                        traces_sample_rate=1.0, include_local_variables=False)
        self.new_selector = 'button[data-action="wrong"]'
        first = self.request().json()
        self.request()
        sentry_sdk.flush()
        events = [item.payload.json for envelope in envelopes for item in envelope.items
                  if item.headers.get("type") == "event"]
        grouped = [event for event in events if event.get("fingerprint", [])[:1] == ["mender.runner"]]
        self.assertEqual(len(grouped), 2)
        self.assertEqual(grouped[0]["fingerprint"], grouped[1]["fingerprint"])
        transactions = [item.payload.json for envelope in envelopes for item in envelope.items
                        if item.headers.get("type") == "transaction"]
        transaction = next(t for t in transactions if t["contexts"]["trace"]["trace_id"] == first["trace_id"])
        operations = {span["op"] for span in transaction["spans"]}
        self.assertTrue({"runner.execute", "healer.diagnose", "healer.patch"} <= operations)

    def test_failed_rollback_stops_subsequent_execution(self):
        self.new_selector = 'button[data-action="wrong"]'
        with patch.object(self.app.state.store, "restore", side_effect=OSError("Disk unavailable")):
            payload = self.request().json()
        self.assertEqual(payload["status"], "failed")
        self.assertNotIn("error", payload)
        self.assertEqual(self.recovery_error(), "rollback_failed")
        self.assertEqual(self.request().status_code, 503)

    def test_failed_atomic_replace_preserves_baseline(self):
        replace = os.replace
        calls = 0
        def fail_candidate(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Disk unavailable")
            return replace(*args)
        with patch("services.backend.store.os.replace", side_effect=fail_candidate):
            payload = self.request().json()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(self.selectors(), self.baseline)
        self.assertEqual(list((self.root / "contracts").glob("tmp*")), [])

    def test_reset_uses_backup_and_increments_version(self):
        from services.backend.reset import restore
        self.assertEqual(self.request().json()["status"], "healed")
        backup = next((self.backend / "state").glob("baseline-*.json"))
        with patch("services.backend.reset.Settings.from_env", return_value=self.settings):
            asyncio.run(restore(backup))
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        self.assertEqual(self.selectors()["version"], 3)


class ImportTests(unittest.TestCase):
    def test_app_import_does_not_import_browser_use_or_healer(self):
        result = subprocess.run([sys.executable, "-B", "-c", (
            "import sys; from services.backend.main import app; "
            "assert 'browser_use' not in sys.modules; "
            "assert 'services.backend.healer' not in sys.modules")], cwd=ROOT, capture_output=True,
            check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
