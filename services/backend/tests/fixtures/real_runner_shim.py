"""Test-only adapter from the agreed runner CLI to Person 1's current permit runner.

Not production code. The real runner (services/runner/execute.py on phase-1) does not yet
accept --workflow/--params/--run-id and writes fixed artifact paths. This shim only
translates arguments and relocates artifacts so the backend's real runner contract can be
exercised against the real Playwright run, real portal, and real failure artifacts.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


parser = argparse.ArgumentParser()
parser.add_argument("--workflow", required=True)
parser.add_argument("--params", required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--sentry-trace")
parser.add_argument("--baggage")
args = parser.parse_args()
params = json.loads(args.params)
artifacts = (Path("runs") / args.run_id).resolve()
command = [os.environ["REAL_RUNNER_PYTHON"], os.environ["REAL_RUNNER_SCRIPT"],
           "--selectors", str(Path("contracts/selectors.json").resolve()),
           "--target-url", os.environ["REAL_PORTAL_URL"],
           "--permit-id", params["permit_id"], "--applicant-name", params["applicant_name"],
           "--artifacts-dir", str(artifacts)]
child = subprocess.run(command, capture_output=True, text=True, env={
    **os.environ, "PLAYWRIGHT_BROWSERS_PATH": os.environ["REAL_PLAYWRIGHT_BROWSERS"]})
sys.stdout.write(child.stdout)
sys.stderr.write(child.stderr)
payload = artifacts / "failure_payload.json"
if child.returncode != 0 and payload.is_file():
    (artifacts / "failure_latest.png").replace(artifacts / "failure.png")
    value = json.loads(payload.read_text())
    value["screenshot_path"] = f"runs/{args.run_id}/failure.png"
    payload.write_text(json.dumps(value))
sys.exit(child.returncode)
