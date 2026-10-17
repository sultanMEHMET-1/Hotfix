"""Console presentation must not corrupt diagnostics or workflow data."""

import io
import logging
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from rich.console import Console

from services.backend.terminal import TerminalHandler, clean, configure_logging, show_result


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.console = Console(file=self.stream, width=160, force_terminal=False,
                               emoji=False, markup=False, highlight=False)
        self.handler = TerminalHandler(console=self.console, level=logging.INFO,
                                       show_time=False, show_level=False, show_path=False)

    def record(self, message, level=logging.INFO, name="browser_use.Agent"):
        return logging.LogRecord(name, level, __file__, 1, message, (), None)

    def test_removes_sdk_emoji_and_ansi_without_modifying_original_record(self):
        original = "\x1b[32m\U0001f44d Task completed successfully\x1b[0m"
        record = self.record(original)
        self.handler.emit(record)
        output = self.stream.getvalue()
        self.assertIn("AGENT", output)
        self.assertIn("Task completed successfully", output)
        self.assertNotIn("\U0001f44d", output)
        self.assertNotIn("\x1b", output)
        self.assertEqual(record.getMessage(), original)

    def test_composed_emoji_are_removed_but_labels_and_selectors_are_literal(self):
        value = '\U0001f469\u200d\U0001f4bb \U0001f1fa\U0001f1f8 \u25b6\ufe0f Café 東京 button[data-action="lookup"]'
        cleaned = clean(value)
        self.assertEqual(cleaned, 'Café 東京 button[data-action="lookup"]')
        record = self.record('[bold] literal selector [data-action="lookup"]', name="mender.backend")
        record.phase = "PATCH"
        self.handler.emit(record)
        self.assertIn('[bold] literal selector [data-action="lookup"]', self.stream.getvalue())

    def test_normal_view_hides_memory_noise_and_http_chatter_but_keeps_errors(self):
        for message, name in (("\U0001f9e0 Memory: internal state", "browser_use.Agent"),
                              ("HTTP Request: POST test", "httpx2"),
                              ("AFC is enabled with max remote calls: 10.", "google.genai.models")):
            self.handler.emit(self.record(message, name=name))
        self.assertEqual(self.stream.getvalue(), "")
        self.handler.emit(self.record("\U0001f4cd Step 2:"))
        self.handler.emit(self.record("\U0001f4a5 Provider failed", level=logging.ERROR))
        self.assertIn("Step 2:", self.stream.getvalue())
        self.assertIn("Provider failed", self.stream.getvalue())
        self.assertNotIn("\U0001f4a5", self.stream.getvalue())

    def test_debug_keeps_details_and_tracebacks_without_emoji(self):
        self.handler.setLevel(logging.DEBUG)
        self.handler.emit(self.record("\U0001f9e0 Memory: debug detail"))
        try:
            raise RuntimeError("\U0001f4a5 Provider unavailable")
        except RuntimeError:
            record = self.record("Agent exception", level=logging.ERROR)
            record.exc_info = sys.exc_info()
        self.handler.emit(record)
        output = self.stream.getvalue()
        self.assertIn("Memory: debug detail", output)
        self.assertIn("RuntimeError", output)
        self.assertIn("Provider unavailable", output)
        self.assertNotIn("\U0001f4a5", output)

    def test_configuration_is_idempotent_and_preserves_file_handlers(self):
        root = logging.getLogger()
        browser = logging.getLogger("browser_use.test_terminal")
        before = (root.handlers[:], root.level, browser.handlers[:], browser.propagate)
        with tempfile.TemporaryDirectory() as directory:
            file_handler = logging.FileHandler(Path(directory) / "test.log")
            root.handlers = [file_handler, logging.StreamHandler(io.StringIO())]
            browser.handlers = [logging.StreamHandler(io.StringIO())]
            browser.propagate = False
            try:
                with patch.dict("os.environ", {"MENDER_LOG_LEVEL": "INFO"}):
                    configure_logging()
                    configure_logging()
                self.assertEqual(sum(isinstance(item, TerminalHandler) for item in root.handlers), 1)
                self.assertIn(file_handler, root.handlers)
                self.assertEqual(browser.handlers, [])
                self.assertTrue(browser.propagate)
            finally:
                root.handlers, root.level, browser.handlers, browser.propagate = before
                file_handler.close()

    def test_result_panel_has_verified_selector_diff_and_readable_failure(self):
        payload = {"status": "healed", "execution_time_ms": 1250, "trace_id": "example-trace",
                   "diff": {"old_selector": "#old", "new_selector": 'button[data-action="lookup"]'}}
        show_result(payload, 2, self.console)
        output = self.stream.getvalue()
        self.assertIn("Recovery verified", output)
        self.assertIn("HEALED", output)
        self.assertIn("1.25 s", output)
        self.assertIn('button[data-action="lookup"]', output)
        self.assertNotIn("\x1b", output)
        self.stream.truncate(0)
        self.stream.seek(0)
        show_result({**payload, "status": "failed", "diff": None,
                     "error": {"message": "\U0001f4a5 Replay failed; baseline restored"}}, 3, self.console)
        self.assertIn("Recovery failed", self.stream.getvalue())
        self.assertIn("Replay failed; baseline restored", self.stream.getvalue())
        self.assertNotIn("\U0001f4a5", self.stream.getvalue())

    def test_actual_sdk_logging_is_clean_for_both_import_orders(self):
        root = Path(__file__).resolve().parents[3]
        for import_first in (False, True):
            script = (
                "import logging\n"
                "from services.backend.terminal import configure_logging\n"
                + ("import browser_use\n" if import_first else "")
                + "configure_logging()\n"
                + ("" if import_first else "import browser_use\n")
                + "logging.getLogger('browser_use.Agent.probe').info('\\U0001f4cd Step 2:')\n"
                + "logging.getLogger('browser_use.Agent.probe').error('\\U0001f4a5 Provider failed')\n"
            )
            with self.subTest(import_first=import_first):
                process = subprocess.run([sys.executable, "-B", "-c", script], cwd=root,
                                         capture_output=True, text=True, check=False, timeout=30)
                self.assertEqual(process.returncode, 0, process.stderr)
                output = process.stdout + process.stderr
                self.assertIn("Step 2:", output)
                self.assertIn("Provider failed", output)
                self.assertNotIn("\U0001f4cd", output)
                self.assertNotIn("\U0001f4a5", output)
                self.assertEqual(output.count("Step 2:"), 1)
