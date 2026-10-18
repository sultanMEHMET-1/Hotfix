import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from execute import (
    PER_STEP_TIMEOUT_MS,
    WorkflowFailure,
    _trim_dom,
    _validate_failure_payload,
    load_selector_map,
    write_failure_artifacts,
)
from reset_demo import reset_submit_selector


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class FakePage:
    url = "http://127.0.0.1:3000/permits/apply"

    def locator(self, selector):
        return SimpleNamespace(evaluate=lambda expression: '<button data-action="submit">Submit</button>')

    def screenshot(self, path, full_page):
        Path(path).write_bytes(b"fake png")


class RunnerContractTests(unittest.TestCase):
    def test_per_step_timeout_is_two_seconds(self):
        self.assertEqual(PER_STEP_TIMEOUT_MS, 2_000)

    def test_selector_map_matches_shared_contract(self):
        selector_map = load_selector_map(REPOSITORY_ROOT / "contracts" / "selectors" / "permit-application.json")
        self.assertEqual(selector_map["fields"]["submit_button"], "#submit-btn")

    def test_dom_trim_keeps_changed_submit_button_context(self):
        snippet = _trim_dom("x" * 300 + '<button data-action="submit">Submit</button>' + "y" * 300, "#submit-btn")
        self.assertIn('data-action="submit"', snippet)
        self.assertLessEqual(len(snippet), 1500)

    def test_failure_artifacts_match_required_fields(self):
        selector_map = load_selector_map(REPOSITORY_ROOT / "contracts" / "selectors" / "permit-application.json")
        failure = WorkflowFailure("submit_button", "#submit-btn", TimeoutError("missing selector"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload_path = write_failure_artifacts(FakePage(), selector_map, failure, Path(temporary_directory))
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            _validate_failure_payload(payload)
            self.assertTrue((Path(temporary_directory) / "failure_latest.png").exists())
            self.assertTrue(Path(payload["screenshot_path"]).is_absolute())
            self.assertEqual(payload["failed_step"], "submit_button")

    def test_reset_submit_selector_restores_baseline_and_increments_version(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            selector_path = Path(temporary_directory) / "selectors.json"
            selector_path.write_text(
                json.dumps(
                    {
                        "workflow_id": "permit-application",
                        "target_url": "https://portal.example.gov/permits/apply",
                        "version": 4,
                        "fields": {"submit_button": "button[data-action='submit']"},
                    }
                ),
                encoding="utf-8",
            )
            changed, version = reset_submit_selector(selector_path)
            selector_map = json.loads(selector_path.read_text(encoding="utf-8"))
            self.assertTrue(changed)
            self.assertEqual(version, 5)
            self.assertEqual(selector_map["fields"]["submit_button"], "#submit-btn")
            self.assertEqual(selector_map["version"], 5)

    def test_reset_never_edits_the_file_when_a_listening_backend_fails_to_answer(self):
        from unittest.mock import patch
        from urllib.error import URLError
        from reset_demo import ResetError, reset_through_backend

        with patch("reset_demo.urlopen", side_effect=URLError(ConnectionRefusedError())):
            self.assertIsNone(reset_through_backend("http://127.0.0.1:8000"))
        for failure in (TimeoutError("timed out"), ConnectionResetError("reset"), URLError(TimeoutError("timed out"))):
            with self.subTest(failure=type(failure).__name__), patch("reset_demo.urlopen", side_effect=failure):
                with self.assertRaises(ResetError):
                    reset_through_backend("http://127.0.0.1:8000")


if __name__ == "__main__":
    unittest.main()
