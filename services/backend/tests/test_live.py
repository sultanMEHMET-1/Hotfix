"""Optional real Gemini -> Browser Use -> Playwright replay smoke test."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from services.backend.config import Settings
from services.backend.main import create_app
from services.backend.tests.test_m1 import workflow_definition
from services.backend.terminal import configure_logging, show_result


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"


@unittest.skipUnless(os.getenv("MENDER_LIVE_TEST") == "1", "Set MENDER_LIVE_TEST=1 to enable paid Gemini calls")
class LiveTest(unittest.TestCase):
    def test_gemini_recovers_one_field_then_playwright_and_canary_pass(self):
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
                "fields": {"input_reference": 'input[data-testid="lookup-reference"]', "submit_button": "#old-lookup"},
            }
            (root / "contracts/selectors.json").write_text(json.dumps(selector_map))
            executable = os.getenv("MENDER_BROWSER_EXECUTABLE")
            chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if not executable and Path(chrome).is_file():
                executable = chrome
            settings = Settings(root=root, runner_script=FIXTURES / "playwright_runner.py",
                                browser_executable=executable)
            with patch.dict(os.environ, {"MENDER_BROWSER_EXECUTABLE": executable or "",
                                         "ANONYMIZED_TELEMETRY": "false", "SENTRY_DSN": ""}):
                with TestClient(create_app(settings)) as client:
                    record_id = "live-" + uuid4().hex[:8]
                    response = client.post("/api/v1/run-workflow", json={"workflow": "sample-lookup", "params": {"record_id": record_id}})
                    payload = response.json()
                    version = json.loads((root / "contracts/selectors.json").read_text())["version"]
                    show_result(payload, version)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(payload["status"], "healed", payload.get("error"))
                    self.assertEqual(payload["data"], {"record_id": record_id, "status": "found"})
                    self.assertEqual(json.loads((root / "contracts/selectors.json").read_text())["version"], 2)
