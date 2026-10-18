"""M3 against Person 1's real Playwright runner and portal. Opt in with MENDER_REAL_RUNNER=1.

The runner is reached through a test-only CLI shim (see fixtures/real_runner_shim.py).
Mocked-agent tests are free; the Gemini test also needs MENDER_LIVE_TEST=1.
"""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from fastapi.testclient import TestClient

from contracts.api_types import HealEvidence
from services.backend.config import Settings
from services.backend.healer import Candidate
from services.backend.main import create_app

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"
VENV_PYTHON = ROOT / ".venv/bin/python"
SUBMIT = '#submit-btn'
HEALED = 'button[data-action="submit"]'
PARAMS = {"permit_id": "PERMIT-2026-0042", "applicant_name": "Davis Municipal Works"}

DEFINITION = json.loads((ROOT / "services/backend/workflows/permit-application.json").read_text())


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(os.getenv("MENDER_REAL_RUNNER") == "1" and VENV_PYTHON.is_file(),
                     "Set MENDER_REAL_RUNNER=1 after services/runner/setup_venv.sh")
class RealRunnerTests(unittest.TestCase):
    def setUp(self):
        port = free_port()
        self.portal = f"http://127.0.0.1:{port}"
        process = subprocess.Popen([str(VENV_PYTHON), str(ROOT / "services/portal/server.py"), "--port", str(port)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.terminate)
        for _ in range(50):
            try:
                urlopen(f"{self.portal}/healthz", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "contracts", self.root / "contracts")
        (self.root / "services/backend/workflows").mkdir(parents=True)
        (self.root / "services/backend/workflows/permit-application.json").write_text(json.dumps(DEFINITION))
        # The checked-in map points at portal.example.gov; the backend rejects failures from another origin.
        self.baseline = json.loads((ROOT / "contracts/selectors.json").read_text())
        self.baseline["target_url"] = f"{self.portal}/permits/apply"
        self.path = self.root / "contracts/selectors.json"
        self.path.write_text(json.dumps(self.baseline))
        env = patch.dict(os.environ, {
            "SENTRY_DSN": "", "REAL_RUNNER_PYTHON": str(VENV_PYTHON), "REAL_PORTAL_URL": self.portal,
            "REAL_RUNNER_SCRIPT": str(ROOT / "services/runner/execute.py"),
            "REAL_PLAYWRIGHT_BROWSERS": str(ROOT / ".venv/playwright-browsers"), "ANONYMIZED_TELEMETRY": "false"})
        env.start()
        self.addCleanup(env.stop)
        self.settings = Settings(root=self.root, runner_script=FIXTURES / "real_runner_shim.py", runner_timeout=30)
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def chaos(self, enabled):
        urlopen(Request(f"{self.portal}/chaos", json.dumps({"enabled": enabled}).encode(),
                        {"content-type": "application/json"}, method="POST"), timeout=2).read()

    def request(self):
        return self.client.post("/api/v1/run-workflow", json={"workflow": "permit-application", "params": PARAMS})

    def selectors(self):
        return json.loads(self.path.read_text())

    def mocked_agent(self, selector):
        calls = []
        evidence = HealEvidence(action_type="click", history_step=0, action_index=0, node_name="BUTTON",
                                attributes={"data-action": "submit"}, reasoning="Mocked unique executed click")
        async def diagnose(settings, workflow, params, failure, **kwargs):
            calls.append(failure.failed_step)
            return Candidate(selector, evidence, metrics={"cost_usd": 0.001, "total_tokens": 1})
        self.client.app.state.diagnose = diagnose
        return calls

    def test_fast_path_against_the_real_runner(self):
        started = time.perf_counter()
        payload = self.request().json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"], {"status": "Approved", "inspector": "Davis", "permit_id": PARAMS["permit_id"]})
        self.assertFalse(payload["recovery_attempted"])
        print(f"real fast path request: {(time.perf_counter() - started) * 1000:.0f} ms")

    def test_chaos_heals_with_real_replay_and_canary(self):
        self.chaos(True)
        calls = self.mocked_agent(HEALED)
        payload = self.request().json()
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(calls, ["submit_button"])
        self.assertEqual(self.selectors()["fields"]["submit_button"], HEALED)
        self.assertEqual([(r["verification_outcome"], r["version_before"], r["version_after"]) for r in payload["heal_records"]],
                         [("committed", 1, 2)])
        self.assertEqual(self.request().json()["status"], "success")

    def test_cooldown_hits_with_real_failure_artifacts(self):
        """Real chaos artifacts embed a randomized class, so the key must ignore classes."""
        self.chaos(True)
        calls = self.mocked_agent("#still-wrong")
        first = self.request().json()
        self.assertEqual(first["status"], "failed", first)
        self.assertEqual(first["heal_records"][0]["verification_outcome"], "rolled_back")
        self.assertEqual(self.selectors()["fields"], self.baseline["fields"])
        second = self.request().json()
        self.assertEqual(calls, ["submit_button"], "second real failure must be served from the cooldown")
        self.assertEqual(second["error"], first["error"])
        self.assertEqual(second["heal_records"], first["heal_records"])

    @unittest.skipUnless(os.getenv("MENDER_LIVE_TEST") == "1", "Set MENDER_LIVE_TEST=1 for paid Gemini calls")
    def test_gemini_heals_the_real_portal(self):
        from dotenv import load_dotenv
        load_dotenv(ROOT / "services/backend/.env", override=False)
        self.client.app.state.diagnose = None
        self.chaos(True)
        started = time.perf_counter()
        payload = self.request().json()
        print(f"real Gemini heal: {(time.perf_counter() - started):.1f} s; "
              f"cost {payload.get('agent_cost_usd')}; agent_ms {payload.get('agent_duration_ms')}; "
              f"selector {self.selectors()['fields']['submit_button']}")
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(payload["heal_records"][0]["verification_outcome"], "committed")
        self.assertEqual(self.request().json()["status"], "success")


if __name__ == "__main__":
    unittest.main()
