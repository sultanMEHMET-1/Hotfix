#!/usr/bin/env python3
"""Run the deterministic permit workflow and emit contract-shaped failures."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit


PER_STEP_TIMEOUT_MS = 2_000
DOM_SNIPPET_LIMIT = 1_500
DEFAULT_PERMIT_ID = "PERMIT-2026-0042"
DEFAULT_APPLICANT_NAME = "Davis Municipal Works"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACTS_DIR = REPOSITORY_ROOT / "contracts"
DEFAULT_SELECTOR_PATH = DEFAULT_CONTRACTS_DIR / "selectors" / "permit-application.json"
DEFAULT_SCHEMA_PATH = REPOSITORY_ROOT / "contracts" / "selectors.schema.json"
DEFAULT_FAILURE_SCHEMA_PATH = REPOSITORY_ROOT / "contracts" / "failure_payload.schema.json"
DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_PLAYWRIGHT_BROWSERS_PATH = REPOSITORY_ROOT / ".venv" / "playwright-browsers"


class RunnerConfigurationError(Exception):
    """Raised when a selector file or command-line configuration is invalid."""


@dataclass
class WorkflowFailure(Exception):
    failed_step: str
    expected_selector: str
    cause: Exception

    def __str__(self) -> str:
        return f"{self.failed_step} failed for {self.expected_selector}: {self.cause}"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file_handle:
            value = json.load(file_handle)
    except (OSError, json.JSONDecodeError) as error:
        raise RunnerConfigurationError(f"Could not read JSON file {path}: {error}") from error
    if not isinstance(value, dict):
        raise RunnerConfigurationError(f"JSON file {path} must contain an object")
    return value


def _is_uri(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return bool(parsed.scheme and parsed.netloc)


def load_selector_map(path: Path = DEFAULT_SELECTOR_PATH) -> dict[str, Any]:
    """Load and validate the selector contract without importing shared code."""

    selector_map = _read_json(path)
    required = {"workflow_id", "target_url", "version", "fields"}
    if set(selector_map) != required:
        raise RunnerConfigurationError(
            f"Selector map must contain exactly {sorted(required)}; got {sorted(selector_map)}"
        )
    workflow_id = selector_map["workflow_id"]
    if not isinstance(workflow_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", workflow_id):
        raise RunnerConfigurationError("workflow_id must be a lowercase kebab-case string")
    if not _is_uri(selector_map["target_url"]):
        raise RunnerConfigurationError("target_url must be an absolute URI")
    if not isinstance(selector_map["version"], int) or isinstance(selector_map["version"], bool):
        raise RunnerConfigurationError("version must be an integer")
    if selector_map["version"] < 1:
        raise RunnerConfigurationError("version must be at least 1")
    fields = selector_map["fields"]
    if not isinstance(fields, dict) or not fields:
        raise RunnerConfigurationError("fields must be a non-empty object")
    for name, selector in fields.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise RunnerConfigurationError(f"Invalid field name: {name!r}")
        if not isinstance(selector, str) or not selector.strip():
            raise RunnerConfigurationError(f"Selector for {name!r} must be a non-empty string")
    return selector_map


def _selector(fields: dict[str, str], name: str) -> str:
    try:
        return fields[name]
    except KeyError as error:
        raise RunnerConfigurationError(f"Selector map is missing required field {name!r}") from error


FIELD_NAME = re.compile(r"[a-z][a-z0-9_]*")
READ_FORM = re.compile(r"text|attr:[A-Za-z_][A-Za-z0-9_:.-]*")


def load_definition(path: Path) -> dict[str, Any]:
    """Read a workflow definition (contracts/workflows/<id>.json) with a small hand-written check.

    The runner's venv has only Playwright, so it cannot import the shared pydantic model.
    """

    definition = _read_json(path)
    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RunnerConfigurationError("Workflow needs a non-empty steps list")
    for step in steps:
        if not isinstance(step, dict) or not FIELD_NAME.fullmatch(str(step.get("field", ""))):
            raise RunnerConfigurationError(f"Invalid workflow step: {step!r}")
        if step.get("action_type") not in ("input", "click"):
            raise RunnerConfigurationError(f"Unsupported action_type for {step['field']!r}")
        if step["action_type"] == "input" and not step.get("param"):
            raise RunnerConfigurationError(f"Input step {step['field']!r} needs a param")
    outputs = definition.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise RunnerConfigurationError("Workflow needs outputs to read")
    for key, spec in outputs.items():
        if not isinstance(spec, dict) or not FIELD_NAME.fullmatch(str(spec.get("field", ""))):
            raise RunnerConfigurationError(f"Invalid output {key!r}")
        if not READ_FORM.fullmatch(str(spec.get("read", ""))):
            raise RunnerConfigurationError(f"Output {key!r} must read 'text' or 'attr:<name>'")
    return definition


def execute_definition(
    page: Any,
    selector_map: dict[str, Any],
    definition: dict[str, Any],
    params: dict[str, Any],
    target_url: str,
    timings: dict[str, float] | None = None,
) -> dict[str, str]:
    """Run any workflow: open the page, perform the ordered steps, then read each output.

    If `timings` is given it receives goto, steps and reads in milliseconds, for observability.
    """

    timings = timings if timings is not None else {}
    fields = selector_map["fields"]
    page.set_default_timeout(PER_STEP_TIMEOUT_MS)
    page.set_default_navigation_timeout(PER_STEP_TIMEOUT_MS)
    mark = perf_counter()
    try:
        page.goto(target_url, wait_until="domcontentloaded")
    except Exception as error:
        raise WorkflowFailure("navigation", target_url, error) from error
    timings["goto"], mark = (perf_counter() - mark) * 1000, perf_counter()

    for step in definition["steps"]:
        selector = _selector(fields, step["field"])
        try:
            locator = page.locator(selector)
            if step["action_type"] == "input":
                locator.fill(str(params[step["param"]]))
            else:
                locator.click()
        except Exception as error:
            raise WorkflowFailure(step["field"], selector, error) from error

    timings["steps"], mark = (perf_counter() - mark) * 1000, perf_counter()
    result: dict[str, str] = {}
    visible: set[str] = set()
    for key, spec in definition["outputs"].items():
        selector = _selector(fields, spec["field"])
        try:
            locator = page.locator(selector)
            if spec["field"] not in visible:  # the result may appear after an async update
                locator.wait_for(state="visible", timeout=PER_STEP_TIMEOUT_MS)
                visible.add(spec["field"])
            if spec["read"] == "text":
                value = locator.inner_text()
            else:
                attribute = spec["read"].removeprefix("attr:")
                value = locator.get_attribute(attribute) or ""
            value = value.strip()
            if not value:
                raise ValueError(f"output {key!r} is empty ({spec['read']})")
        except Exception as error:
            raise WorkflowFailure(spec["field"], selector, error) from error
        result[key] = value
    timings["reads"] = (perf_counter() - mark) * 1000
    return result


def _trim_dom(html: str, expected_selector: str) -> str:
    compact_html = re.sub(r"\s+", " ", html).strip()
    search_terms = [expected_selector.lstrip("#.")]
    if "submit" in expected_selector:
        search_terms.extend(["data-action=\"submit\"", "data-action='submit'"])
    start = next((compact_html.find(term) for term in search_terms if compact_html.find(term) >= 0), 0)
    start = max(0, start - DOM_SNIPPET_LIMIT // 2)
    return compact_html[start : start + DOM_SNIPPET_LIMIT]


def _dom_context(page: Any, expected_selector: str) -> str:
    for container_selector in ("form", "main", "body"):
        try:
            html = page.locator(container_selector).evaluate("element => element.outerHTML")
            return _trim_dom(str(html), expected_selector)
        except Exception:
            continue
    try:
        return _trim_dom(str(page.content()), expected_selector)
    except Exception as error:
        return f"<dom-unavailable>{error}</dom-unavailable>"


def _validate_failure_payload(payload: dict[str, Any]) -> None:
    required = {
        "workflow_id",
        "timestamp",
        "failed_step",
        "expected_selector",
        "page_url",
        "dom_snippet",
        "screenshot_path",
        "error_message",
    }
    if set(payload) != required:
        raise ValueError(f"Failure payload fields differ from contract: {sorted(payload)}")
    if not isinstance(payload["workflow_id"], str) or not payload["workflow_id"]:
        raise ValueError("workflow_id must be a non-empty string")
    if not isinstance(payload["timestamp"], (int, float)) or isinstance(payload["timestamp"], bool):
        raise ValueError("timestamp must be numeric")
    for field in required - {"timestamp"}:
        if not isinstance(payload[field], str) or not payload[field]:
            raise ValueError(f"{field} must be a non-empty string")
    if not _is_uri(payload["page_url"]):
        raise ValueError("page_url must be an absolute URI")


def write_failure_artifacts(
    page: Any,
    selector_map: dict[str, Any],
    failure: WorkflowFailure,
    artifacts_dir: Path,
    screenshot_name: str = "failure_latest.png",
) -> Path:
    """Capture screenshot and DOM context, then validate and write the payload."""

    artifacts_dir = artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = (artifacts_dir / screenshot_name).resolve()
    payload_path = artifacts_dir / "failure_payload.json"
    screenshot_error: Exception | None = None
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as error:
        screenshot_error = error
    try:
        page_url = page.url
    except Exception:
        page_url = selector_map["target_url"]
    message = f"{type(failure.cause).__name__}: {failure.cause} (selector {failure.expected_selector})"
    if screenshot_error is not None:
        message += f"; screenshot capture failed: {screenshot_error}"
    payload = {
        "workflow_id": selector_map["workflow_id"],
        "timestamp": int(time.time() * 1000),
        "failed_step": failure.failed_step,
        "expected_selector": failure.expected_selector,
        "page_url": page_url,
        "dom_snippet": _dom_context(page, failure.expected_selector),
        "screenshot_path": str(screenshot_path),
        "error_message": message,
    }
    _validate_failure_payload(payload)
    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload_path


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    # Backend runner contract: --workflow <id> --params '<json>' --run-id <uuid>. Artifacts go to
    # runs/<run_id>/ (failure_payload.json, failure.png) relative to the working directory.
    parser.add_argument("--workflow", default="permit-application")
    parser.add_argument("--params", help="JSON object with the workflow's parameters")
    parser.add_argument("--run-id")
    parser.add_argument("--sentry-trace")
    parser.add_argument("--baggage")
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS_DIR,
                        help="Folder with workflows/<id>.json and selectors/<id>.json")
    parser.add_argument("--selectors", type=Path, help="Override the selector map path")
    parser.add_argument("--target-url", help="Override the map's target_url")
    parser.add_argument("--permit-id", default=DEFAULT_PERMIT_ID, help="Permit workflow only, when --params is absent")
    parser.add_argument("--applicant-name", default=DEFAULT_APPLICANT_NAME, help="Permit workflow only, when --params is absent")
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--headed", action="store_true", help="Show the browser while executing")
    return parser


def _parameters(args: argparse.Namespace) -> dict[str, Any]:
    if args.params:
        try:
            params = json.loads(args.params)
        except ValueError as error:
            raise RunnerConfigurationError(f"invalid --params: {error}") from error
        if not isinstance(params, dict):
            raise RunnerConfigurationError("--params must be a JSON object")
        return params
    if args.workflow == "permit-application":
        return {"permit_id": args.permit_id, "applicant_name": args.applicant_name}
    raise RunnerConfigurationError("--params is required")


def main(argv: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.workflow):
            raise RunnerConfigurationError(f"invalid workflow id {args.workflow!r}")
        selector_map = load_selector_map(args.selectors or args.contracts / "selectors" / f"{args.workflow}.json")
        if selector_map["workflow_id"] != args.workflow:
            raise RunnerConfigurationError(f"selector map belongs to {selector_map['workflow_id']!r}, not {args.workflow!r}")
        definition = load_definition(args.contracts / "workflows" / f"{args.workflow}.json")
        missing = [name for name in [s["field"] for s in definition["steps"]] + [o["field"] for o in definition["outputs"].values()]
                   if name not in selector_map["fields"]]
        if missing:
            raise RunnerConfigurationError(f"selector map is missing {sorted(set(missing))}")
        params = _parameters(args)
        absent = [s["param"] for s in definition["steps"] if s["action_type"] == "input" and s["param"] not in params]
        if absent:
            raise RunnerConfigurationError(f"missing params {absent}")
    except RunnerConfigurationError as error:
        print(f"runner configuration error: {error}", file=sys.stderr)
        return 2
    try:
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(DEFAULT_PLAYWRIGHT_BROWSERS_PATH))
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "runner dependency missing: run `services/runner/setup_venv.sh`, then use `services/runner/run.sh`",
            file=sys.stderr,
        )
        return 2

    artifacts_dir, screenshot_name = args.artifacts_dir, "failure_latest.png"
    if args.run_id:
        artifacts_dir, screenshot_name = Path("runs") / args.run_id, "failure.png"
    target_url = args.target_url or selector_map["target_url"]
    try:
        with sync_playwright() as playwright:
            process_started = perf_counter()
            browser = playwright.chromium.launch(
                headless=not args.headed, executable_path=os.environ.get("MENDER_BROWSER_EXECUTABLE") or None)
            timings: dict[str, float] = {}
            try:
                page = browser.new_page()
                timings["launch"] = (perf_counter() - process_started) * 1000
                try:
                    workflow_started = perf_counter()
                    result = execute_definition(page, selector_map, definition, params, target_url, timings)
                except WorkflowFailure as failure:
                    timings["total"] = (perf_counter() - process_started) * 1000
                    print(f"runner_timings_ms={json.dumps({k: round(v, 1) for k, v in timings.items()})}", file=sys.stderr)
                    payload_path = write_failure_artifacts(page, selector_map, failure, artifacts_dir, screenshot_name)
                    print(f"runner failed: {failure}; wrote {payload_path}", file=sys.stderr)
                    return 1
                elapsed_ms = (perf_counter() - workflow_started) * 1000
                timings["total"] = (perf_counter() - process_started) * 1000
                print(json.dumps(result))
                print(f"workflow_latency_ms={elapsed_ms:.2f}", file=sys.stderr)
                print(f"runner_timings_ms={json.dumps({k: round(v, 1) for k, v in timings.items()})}", file=sys.stderr)
                return 0
            finally:
                browser.close()
    except Exception as error:
        print(f"runner error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
