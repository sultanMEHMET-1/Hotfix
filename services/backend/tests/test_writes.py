"""Write workflows: the local-only guard, and healing a save button on the local sandbox site."""

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

import httpx
from fastapi.testclient import TestClient

from contracts.api_types import HealEvidence
from services.backend.config import write_allowed
from services.backend.healer import Candidate
from services.backend.main import create_app
from services.backend.tests.test_m1 import CORRECT
from services.backend.tests.test_m2 import M2Harness

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"
SAVE = 'button[data-action="save"]'

RECORD_UPDATE = {
    "goal": "Enter the record ID and the new value, save the record exactly once, and report the saved value.",
    "steps": [
        {"field": "input_record_id", "action_type": "input", "role": "textbox", "label": "Record ID"},
        {"field": "input_value", "action_type": "input", "role": "textbox", "label": "New value"},
        {"field": "save_button", "action_type": "click", "role": "button", "label": "Save record"},
    ],
    "params_schema": {"type": "object", "required": ["record_id", "value"], "additionalProperties": False,
                      "properties": {"record_id": {"type": "string"}, "value": {"type": "string"}}},
    "output_schema": {"type": "object", "required": ["record_id", "value"], "additionalProperties": False,
                      "properties": {"record_id": {"type": "string"}, "value": {"type": "string"}}},
    "canary": {"params": {"record_id": "canary-record", "value": "canary-value"},
               "expected_output": {"record_id": "canary-record", "value": "canary-value"}},
    "mutates": True,
}


class WriteGuardTests(unittest.TestCase):
    def test_only_loopback_and_allowlisted_hosts_may_be_written_to(self):
        for url in ("http://127.0.0.1:3100/records", "http://localhost/x", "http://[::1]:8/x"):
            self.assertTrue(write_allowed(url), url)
        for url in ("https://portal.example.gov/x", "http://127.0.0.1.evil.com/x", "http://127.0.0.1@evil.com/x", "not a url"):
            self.assertFalse(write_allowed(url), url)
        self.assertTrue(write_allowed("https://staging.corp.test/x", ("staging.corp.test",)))


class WriteRefusalTests(M2Harness):
    async def served(self, target_url, hosts=()):
        (self.settings.backend / "workflows/sample-lookup.json").write_text(json.dumps({**self.definition, "mutates": True}))
        self.path.write_text(json.dumps({**self.baseline, "target_url": target_url,
                                         "fields": {"submit_button": CORRECT, "input_reference": "#reference"}}))
        app = create_app(replace(self.settings, write_hosts=hosts))
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        self.addAsyncCleanup(lifespan.__aexit__, None, None, None)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://backend.test")
        self.addAsyncCleanup(client.aclose)
        return (await client.post("/api/v1/run-workflow", json={"workflow": "sample-lookup", "params": {"record_id": "r"}})).json()

    async def test_public_site_is_refused_before_the_runner_starts(self):
        payload = await self.served("http://portal.test/lookup")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["code"], "write_not_allowed")
        self.assertFalse(payload["recovery_attempted"])
        self.assertFalse((self.root / "runs").exists(), "the runner must not have been started")

    async def test_loopback_and_allowlisted_sites_run(self):
        self.assertEqual((await self.served("http://127.0.0.1:3100/records"))["status"], "success")
        self.assertEqual((await self.served("http://portal.test/lookup", ("portal.test",)))["status"], "success")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(os.getenv("MENDER_BROWSER_TEST") == "1", "Set MENDER_BROWSER_TEST=1 (needs Chrome and playwright)")
class SandboxSiteTests(unittest.TestCase):
    def setUp(self):
        port = free_port()
        self.site = f"http://127.0.0.1:{port}"
        server = subprocess.Popen([sys.executable, str(ROOT / "services/backend/sandbox/records_site.py"), "--port", str(port)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(server.wait)
        self.addCleanup(server.terminate)
        for _ in range(50):
            try:
                urlopen(f"{self.site}/healthz", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "contracts", self.root / "contracts")
        (self.root / "services/backend/workflows").mkdir(parents=True)
        (self.root / "services/backend/workflows/record-update.json").write_text(json.dumps(RECORD_UPDATE))
        self.baseline = {"workflow_id": "record-update", "target_url": f"{self.site}/records", "version": 1,
                         "fields": {"input_record_id": "#record-id", "input_value": "#record-value",
                                    "save_button": "#save-btn", "saved_value": "[data-testid='saved-value']"}}
        (self.root / "contracts/selectors.json").write_text(json.dumps(self.baseline))
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        executable = os.getenv("MENDER_BROWSER_EXECUTABLE") or (chrome if Path(chrome).is_file() else "")
        env = patch.dict(os.environ, {"SENTRY_DSN": "", "MENDER_BROWSER_EXECUTABLE": executable, "ANONYMIZED_TELEMETRY": "false"})
        env.start()
        self.addCleanup(env.stop)
        from services.backend.config import Settings
        self.settings = Settings(root=self.root, runner_script=FIXTURES / "sandbox_runner.py", runner_timeout=30,
                                 browser_executable=executable or None)
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def post(self, path, body):
        return json.load(urlopen(Request(f"{self.site}{path}", json.dumps(body).encode(), method="POST"), timeout=3))

    def state(self):
        return json.load(urlopen(f"{self.site}/state", timeout=3))

    def request(self, record_id="rec-1", value="hello"):
        return self.client.post("/api/v1/run-workflow",
                                json={"workflow": "record-update", "params": {"record_id": record_id, "value": value}}).json()

    def test_save_works_and_the_site_really_changes(self):
        payload = self.request()
        self.assertEqual((payload["status"], payload["data"]), ("success", {"record_id": "rec-1", "value": "hello"}))
        self.assertEqual(self.state()["records"], {"rec-1": "hello"})

    def test_chaos_heal_repeats_the_write_idempotently(self):
        self.post("/chaos", {"enabled": True})
        evidence = HealEvidence(action_type="click", history_step=0, action_index=0, node_name="BUTTON",
                                attributes={"data-action": "save"}, reasoning="Mocked unique executed click")
        async def diagnose(settings, workflow, params, failure, **kwargs):
            return Candidate(SAVE, evidence, metrics={"cost_usd": 0.001, "total_tokens": 1})
        self.client.app.state.diagnose = diagnose
        payload = self.request()
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(payload["heal_records"][0]["verification_outcome"], "committed")
        state = self.state()
        # Replay and canary each write once; repeating a set with the same value changes nothing else.
        self.assertEqual(state["records"], {"rec-1": "hello", "canary-record": "canary-value"})
        self.assertEqual(state["writes"], 2)

    @unittest.skipUnless(os.getenv("MENDER_LIVE_TEST") == "1", "Set MENDER_LIVE_TEST=1 for paid Gemini calls")
    def test_gemini_heals_the_save_button_on_the_sandbox(self):
        from dotenv import load_dotenv
        load_dotenv(ROOT / "services/backend/.env", override=False)
        self.client.app.state.diagnose = None
        self.post("/chaos", {"enabled": True})
        started = time.perf_counter()
        payload = self.request("live-rec", "live-value")
        state = self.state()
        print(f"sandbox Gemini heal: {time.perf_counter() - started:.1f} s; cost {payload.get('agent_cost_usd')}; "
              f"agent_ms {payload.get('agent_duration_ms')}; writes {state['writes']}; "
              f"selector {json.loads((self.root / 'contracts/selectors.json').read_text())['fields']['save_button']}")
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(state["records"].get("live-rec"), "live-value")
        self.assertEqual(state["records"].get("canary-record"), "canary-value")
        self.assertEqual(self.request("after", "x")["status"], "success")


if __name__ == "__main__":
    unittest.main()
