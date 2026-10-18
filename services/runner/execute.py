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
DEFAULT_TARGET_URL = "http://127.0.0.1:3000/permits/apply"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTOR_PATH = REPOSITORY_ROOT / "contracts" / "selectors.json"
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


def execute_workflow(
    page: Any,
    selector_map: dict[str, Any],
    permit_id: str,
    applicant_name: str,
    target_url: str,
) -> dict[str, str]:
    """Execute the fixed workflow on an existing Playwright page."""

    fields = selector_map["fields"]
    permit_selector = _selector(fields, "input_permit_id")
    applicant_selector = _selector(fields, "input_applicant_name")
    submit_selector = _selector(fields, "submit_button")
    status_selector = _selector(fields, "status_badge")
    page.set_default_timeout(PER_STEP_TIMEOUT_MS)
    page.set_default_navigation_timeout(PER_STEP_TIMEOUT_MS)

    steps = (
        ("navigation", target_url, lambda: page.goto(target_url, wait_until="domcontentloaded")),
        ("input_permit_id", permit_selector, lambda: page.locator(permit_selector).fill(permit_id)),
        (
            "input_applicant_name",
            applicant_selector,
            lambda: page.locator(applicant_selector).fill(applicant_name),
        ),
        ("submit_button", submit_selector, lambda: page.locator(submit_selector).click()),
    )
    for failed_step, expected_selector, action in steps:
        try:
            action()
        except Exception as error:
            raise WorkflowFailure(failed_step, expected_selector, error) from error

    try:
        status_badge = page.locator(status_selector)
        status_badge.wait_for(state="visible", timeout=PER_STEP_TIMEOUT_MS)
        status = status_badge.inner_text().strip()
        inspector = status_badge.get_attribute("data-inspector")
        permit_id_echo = status_badge.get_attribute("data-permit")
        if not status or not inspector or not permit_id_echo:
            raise ValueError("status badge did not contain status, inspector and permit data")
    except Exception as error:
        raise WorkflowFailure("status_badge", status_selector, error) from error
    return {"status": status, "inspector": inspector, "permit_id": permit_id_echo}


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
        page_url = "http://127.0.0.1:3000/permits/apply"
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


def _default_target_url(cli_target_url: str | None) -> str:
    if cli_target_url:
        return cli_target_url
    return DEFAULT_TARGET_URL


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selectors", type=Path, default=DEFAULT_SELECTOR_PATH)
    parser.add_argument("--target-url", help="Override the target URL; defaults to the local portal")
    parser.add_argument("--permit-id", default=DEFAULT_PERMIT_ID)
    parser.add_argument("--applicant-name", default=DEFAULT_APPLICANT_NAME)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--headed", action="store_true", help="Show the browser while executing")
    # Backend runner contract: --workflow <id> --params '<json>' --run-id <uuid>. Artifacts go to
    # runs/<run_id>/ (failure_payload.json, failure.png) relative to the working directory.
    parser.add_argument("--workflow")
    parser.add_argument("--params", help="JSON object with permit_id and applicant_name")
    parser.add_argument("--run-id")
    parser.add_argument("--sentry-trace")
    parser.add_argument("--baggage")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        selector_map = load_selector_map(args.selectors)
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

    permit_id, applicant_name = args.permit_id, args.applicant_name
    artifacts_dir, screenshot_name = args.artifacts_dir, "failure_latest.png"
    if args.workflow and args.workflow != selector_map["workflow_id"]:
        print(f"runner configuration error: unknown workflow {args.workflow!r}", file=sys.stderr)
        return 2
    if args.params:
        try:
            params = json.loads(args.params)
            permit_id, applicant_name = params["permit_id"], params["applicant_name"]
        except (ValueError, KeyError, TypeError) as error:
            print(f"runner configuration error: invalid --params: {error}", file=sys.stderr)
            return 2
    if args.run_id:
        artifacts_dir, screenshot_name = Path("runs") / args.run_id, "failure.png"
    target_url = _default_target_url(args.target_url)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            try:
                page = browser.new_page()
                try:
                    workflow_started = perf_counter()
                    result = execute_workflow(
                        page,
                        selector_map,
                        permit_id,
                        applicant_name,
                        target_url,
                    )
                except WorkflowFailure as failure:
                    payload_path = write_failure_artifacts(page, selector_map, failure, artifacts_dir, screenshot_name)
                    print(f"runner failed: {failure}; wrote {payload_path}", file=sys.stderr)
                    return 1
                elapsed_ms = (perf_counter() - workflow_started) * 1000
                print(json.dumps(result))
                print(f"workflow_latency_ms={elapsed_ms:.2f}", file=sys.stderr)
                return 0
            finally:
                browser.close()
    except Exception as error:
        print(f"runner error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
