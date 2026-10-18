#!/usr/bin/env python3
"""Restore the local portal and selector map to the Normal Mode demo baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASELINE_SUBMIT_SELECTOR = "#submit-btn"
DEFAULT_PORTAL_URL = "http://127.0.0.1:3000"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTOR_PATH = REPOSITORY_ROOT / "contracts" / "selectors.json"


class ResetError(Exception):
    """Raised when the local demo cannot be restored safely."""


def disable_chaos_mode(portal_url: str) -> None:
    endpoint = f"{portal_url.rstrip('/')}/chaos"
    request = Request(
        endpoint,
        data=b'{"enabled": false}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=2) as response:
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise ResetError(f"Could not disable Chaos Mode at {endpoint}: {error}") from error
    if payload.get("enabled") is not False:
        raise ResetError(f"Portal did not confirm Chaos Mode was disabled: {payload}")


def reset_through_backend(backend_url: str) -> int | None:
    """Reset under the backend's selector lock. Returns None only if no backend is listening."""

    request = Request(f"{backend_url.rstrip('/')}/api/v1/admin/reset", data=b"{}", method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            return int(json.load(response)["version"])
    except HTTPError as error:
        raise ResetError(f"Backend refused the reset (HTTP {error.code}); retry when it is idle") from error
    except (URLError, OSError):
        return None


def reset_submit_selector(selector_path: Path) -> tuple[bool, int]:
    try:
        selector_map = json.loads(selector_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ResetError(f"Could not read selector map {selector_path}: {error}") from error
    fields = selector_map.get("fields")
    version = selector_map.get("version")
    if not isinstance(fields, dict) or not isinstance(version, int) or isinstance(version, bool):
        raise ResetError("Selector map must contain object fields and an integer version")
    if fields.get("submit_button") == BASELINE_SUBMIT_SELECTOR:
        return False, version
    fields["submit_button"] = BASELINE_SUBMIT_SELECTOR
    selector_map["version"] = version + 1
    try:
        selector_path.write_text(json.dumps(selector_map, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise ResetError(f"Could not write selector map {selector_path}: {error}") from error
    return True, version + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portal-url", default=DEFAULT_PORTAL_URL)
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--selectors", type=Path, default=DEFAULT_SELECTOR_PATH)
    args = parser.parse_args(argv)
    try:
        disable_chaos_mode(args.portal_url)
        backend_version = reset_through_backend(args.backend_url)
        if backend_version is not None:
            print(f"Chaos Mode disabled; backend restored the original selectors at version {backend_version}.")
            return 0
        selector_changed, version = reset_submit_selector(args.selectors)
    except ResetError as error:
        print(f"demo reset error: {error}", file=sys.stderr)
        return 1
    selector_message = "restored" if selector_changed else "already at baseline"
    print(f"Chaos Mode disabled; submit selector {selector_message} at version {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
