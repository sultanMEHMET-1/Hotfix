"""Optional real Gemini -> Browser Use -> Playwright replay smoke test."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from services.backend.config import Settings
from services.backend.main import create_app
from services.backend.tests.test_m1 import workflow_definition
from services.backend.terminal import configure_logging, show_result
from services.backend.store import atomic_json


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"


@unittest.skipUnless(os.getenv("MENDER_LIVE_TEST") == "1", "Set MENDER_LIVE_TEST=1 to enable paid Gemini calls")
class LiveTest(unittest.TestCase):
    def test_gemini_recovers_one_field_then_playwright_and_canary_pass(self):
        self.run_recovery(two_fields=False)

    def test_gemini_recovers_two_fields_then_playwright_and_canary_pass(self):
        self.run_recovery(two_fields=True)

    def run_recovery(self, two_fields):
        started = time.perf_counter()
        from dotenv import load_dotenv
        load_dotenv(ROOT / "services/backend/.env", override=False)
        self.assertTrue(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"), "A Gemini key is required")
        self.assertTrue(os.getenv("GEMINI_MODEL"), "A model must be selected explicitly")
        console = configure_logging()
        console.line()
        console.rule("Mender | live recovery", style="cyan")
        page = (FIXTURES / "local_portal.html").read_bytes()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(page)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "contracts", root / "contracts")
            folder = root / "services/backend/workflows"
            folder.mkdir(parents=True)
            definition = workflow_definition()
            definition["goal"] = "Enter the provided record_id into Record reference, click the Look up record button, and report the lookup result."
            (folder / "sample-lookup.json").write_text(json.dumps(definition))
            selector_map = {
                "workflow_id": "sample-lookup", "version": 1,
                "target_url": f"http://127.0.0.1:{server.server_port}/",
                "fields": {"input_reference": "#old-reference" if two_fields else 'input[data-testid="lookup-reference"]', "submit_button": "#old-lookup"},
            }
            (root / "contracts/selectors.json").write_text(json.dumps(selector_map))
            executable = os.getenv("MENDER_BROWSER_EXECUTABLE")
            chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if not executable and Path(chrome).is_file():
                executable = chrome
            settings = Settings(root=root, runner_script=FIXTURES / "playwright_runner.py",
                                browser_executable=executable, headless=os.getenv("MENDER_HEADLESS", "true").lower() != "false")
            with patch.dict(os.environ, {"MENDER_BROWSER_EXECUTABLE": executable or "",
                                         "ANONYMIZED_TELEMETRY": "false", "SENTRY_DSN": ""}):
                with TestClient(create_app(settings)) as client:
                    record_id = "live-" + uuid4().hex[:8]
                    response = client.post("/api/v1/run-workflow", json={"workflow": "sample-lookup", "params": {"record_id": record_id}})
                    payload = response.json()
                    version = json.loads((root / "contracts/selectors.json").read_text())["version"]
                    show_result(payload, version)
                    reports = list((settings.backend / "state").glob("recovery-*.json"))
                    measurement = json.loads(reports[0].read_text()) if reports else {
                        "recovery_id": str(uuid4()), "success": False, "wall_time_ms": None,
                        "attempts": [], "totals": {},
                    }
                    measurement["request_wall_time_ms"] = payload["execution_time_ms"]
        server.shutdown()
        server.server_close()
        measurement["test_wall_time_ms"] = (time.perf_counter() - started) * 1000
        measurement["scenario"] = "two-fields" if two_fields else "button"
        folder = ROOT / "services/backend/state"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"live-{measurement['scenario']}-{measurement['recovery_id']}.json"
        atomic_json(path, measurement)
        console.print(f"Measurements saved: {path}")
        recovery_time = f"{measurement['wall_time_ms'] / 1000:.3f} s" if measurement["wall_time_ms"] is not None else "unknown"
        console.print(f"Request: {measurement['request_wall_time_ms'] / 1000:.3f} s; "
                      f"recovery: {recovery_time}; "
                      f"test: {measurement['test_wall_time_ms'] / 1000:.3f} s")
        console.print(f"Tokens: {measurement['totals']}")
        # Persist outcome and usage before assertions, including unsuccessful healing.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "healed")
        self.assertEqual(payload["data"], {"record_id": record_id, "status": "found"})
        self.assertEqual(version, 3 if two_fields else 2)
        self.assertEqual(len(reports), 1)
        self.assertEqual(len(measurement["attempts"]), 2 if two_fields else 1)
        self.assertTrue(measurement["totals"]["total_tokens_complete"], measurement)
        self.assertGreater(measurement["totals"]["total_tokens"], 0)
