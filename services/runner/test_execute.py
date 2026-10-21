import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from execute import (
    PER_STEP_TIMEOUT_MS,
    REMOTE_NAVIGATION_TIMEOUT_MS,
    RunnerConfigurationError,
    WorkflowFailure,
    _trim_dom,
    _validate_failure_payload,
    execute_definition,
    expand_url,
    load_definition,
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


class RecordingPage:
    """A page that records what the runner does and can be told to fail one selector."""

    def __init__(self, texts=None, attributes=None, fail_on=None):
        self.calls, self.texts, self.attributes, self.fail_on = [], texts or {}, attributes or {}, fail_on

    def set_default_timeout(self, value): pass
    def set_default_navigation_timeout(self, value): self.navigation_timeout = value

    def goto(self, url, wait_until):
        self.calls.append(("goto", url))
        if self.fail_on == "navigation":
            raise TimeoutError("net::ERR_CONNECTION_REFUSED")

    def locator(self, selector):
        page = self

        class Locator:
            def _act(self, name, *args):
                page.calls.append((name, selector, *args))
                if page.fail_on == selector:
                    raise TimeoutError(f"waiting for locator({selector})")

            def fill(self, value): self._act("fill", value)
            def click(self): self._act("click")
            def wait_for(self, state, timeout): self._act("wait_for", state)
            def inner_text(self): return page.texts.get(selector, "")
            def get_attribute(self, name): return page.attributes.get((selector, name))

        return Locator()


class GenericExecutorTests(unittest.TestCase):
    DEFINITION = {
        "steps": [
            {"field": "name_input", "action_type": "input", "param": "name"},
            {"field": "go", "action_type": "click"},
        ],
        "outputs": {"label": {"field": "result", "read": "text"}, "code": {"field": "result", "read": "attr:data-code"}},
    }
    MAP = {"workflow_id": "demo", "version": 1, "target_url": "http://site.test/form",
           "fields": {"name_input": "#n", "go": "#go", "result": "#out"}}

    def run_it(self, page, params=None, url=None):
        return execute_definition(page, self.MAP, self.DEFINITION, params or {"name": "Ada"}, url or self.MAP["target_url"])

    def test_opens_the_maps_url_runs_steps_in_order_then_reads_each_output(self):
        page = RecordingPage(texts={"#out": " Done "}, attributes={("#out", "data-code"): "42"})
        self.assertEqual(self.run_it(page), {"label": "Done", "code": "42"})
        self.assertEqual(page.calls, [("goto", "http://site.test/form"), ("fill", "#n", "Ada"), ("click", "#go"),
                                      ("wait_for", "#out", "visible")])  # waits once for a field read twice

    def test_it_reports_where_the_time_goes_for_observability(self):
        timings = {}
        page = RecordingPage(texts={"#out": "Done"}, attributes={("#out", "data-code"): "42"})
        execute_definition(page, self.MAP, self.DEFINITION, {"name": "Ada"}, self.MAP["target_url"], timings)
        self.assertEqual(sorted(timings), ["goto", "reads", "steps"])
        self.assertTrue(all(value >= 0 for value in timings.values()))

    def test_each_failure_names_the_step_and_selector_the_backend_can_repair(self):
        for fail_on, step, selector in (("navigation", "navigation", "http://site.test/form"), ("#n", "name_input", "#n"),
                                        ("#go", "go", "#go")):
            with self.subTest(fail_on=fail_on):
                with self.assertRaises(WorkflowFailure) as caught:
                    self.run_it(RecordingPage(fail_on=fail_on))
                self.assertEqual((caught.exception.failed_step, caught.exception.expected_selector), (step, selector))

    def test_a_missing_or_empty_read_fails_at_the_output_field(self):
        with self.assertRaises(WorkflowFailure) as caught:
            self.run_it(RecordingPage(texts={"#out": "Done"}))  # attribute missing
        self.assertEqual(caught.exception.failed_step, "result")
        with self.assertRaises(WorkflowFailure):
            self.run_it(RecordingPage(texts={"#out": "  "}, attributes={("#out", "data-code"): "42"}))

    def test_the_real_definitions_load_with_the_hand_written_check(self):
        for name in ("permit-application", "record-update"):
            definition = load_definition(REPOSITORY_ROOT / "contracts" / "workflows" / f"{name}.json")
            self.assertTrue(definition["outputs"])

    def test_remote_sites_get_a_longer_page_load_and_local_ones_keep_two_seconds(self):
        for url, expected in (("http://127.0.0.1:3000/x", PER_STEP_TIMEOUT_MS), ("http://localhost:3100/x", PER_STEP_TIMEOUT_MS),
                              ("https://sa.ucla.edu/ro/public/soc", REMOTE_NAVIGATION_TIMEOUT_MS)):
            with self.subTest(url=url):
                page = RecordingPage(texts={"#out": "x"}, attributes={("#out", "data-code"): "1"})
                self.run_it(page, url=url)
                self.assertEqual(page.navigation_timeout, expected)
        self.assertEqual(REMOTE_NAVIGATION_TIMEOUT_MS, 7_000)

    def test_url_placeholders_are_encoded_and_catalog_numbers_padded(self):
        url = "http://s.test/r?t={term}&subj={subject}&catlg={course_number:catalog}"
        params = {"term": "26F", "subject": "COM SCI", "course_number": "35l"}
        self.assertEqual(expand_url(url, params), "http://s.test/r?t=26F&subj=COM+SCI&catlg=0035L")
        self.assertEqual(expand_url(url, {**params, "course_number": "M51A"}).rsplit("=", 1)[1], "0051A+M")
        self.assertEqual(expand_url("http://s.test/plain", {}), "http://s.test/plain")
        self.assertEqual(expand_url(url, {**params, "course_number": "C121"}).rsplit("=", 1)[1], "0121++C")
        self.assertEqual(expand_url(url, {**params, "course_number": "cm114"}).rsplit("=", 1)[1], "0114++CM")
        for bad in ("", "3 5", "x&y=1", "12345678"):
            with self.subTest(bad=bad), self.assertRaises(RunnerConfigurationError):
                expand_url(url, {**params, "course_number": bad})
        with self.assertRaises(RunnerConfigurationError):
            expand_url(url, {"term": "26F"})

    def test_bad_definitions_are_rejected(self):
        bad = {
            "no steps list": {"outputs": self.DEFINITION["outputs"]},
            "no outputs": {"steps": self.DEFINITION["steps"]},
            "input without param": {"steps": [{"field": "a", "action_type": "input"}], "outputs": self.DEFINITION["outputs"]},
            "hover": {"steps": [{"field": "a", "action_type": "hover"}], "outputs": self.DEFINITION["outputs"]},
            "bad read": {"steps": self.DEFINITION["steps"], "outputs": {"x": {"field": "result", "read": "html"}}},
        }
        for label, definition in bad.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "w.json"
                path.write_text(json.dumps(definition))
                with self.assertRaises(RunnerConfigurationError):
                    load_definition(path)


if __name__ == "__main__":
    unittest.main()
