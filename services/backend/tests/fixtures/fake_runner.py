"""Subprocess test double for Person 1's agreed CLI, not a production runner."""

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time


parser = argparse.ArgumentParser()
parser.add_argument("--workflow", required=True)
parser.add_argument("--params", required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--sentry-trace")
parser.add_argument("--baggage")
args = parser.parse_args()
params = json.loads(args.params)
case = params.get("case")
if case == "hang":
    Path("runner.pid").write_text(str(os.getpid()))
    time.sleep(30)
if case == "junk":
    print("not JSON")
    sys.exit(0)
selectors = json.loads(Path("contracts/selectors.json").read_text())
target = selectors["fields"]["submit_button"]
correct = target == 'button[data-action="lookup"]'
if correct or target == 'button[data-action="poisoned"]':
    record_id = params["record_id"]
    if target == 'button[data-action="poisoned"]':
        record_id = "wrong-record"
    print(json.dumps({"record_id": record_id, "status": "found"}))
    sys.exit(0)
directory = Path("runs") / args.run_id
directory.mkdir(parents=True)
(directory / "failure.png").write_bytes(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jP2kAAAAASUVORK5CYII="
))
failure = {
    "workflow_id": args.workflow,
    "timestamp": time.time() * 1000,
    "failed_step": "submit_button",
    "expected_selector": target,
    "page_url": selectors["target_url"],
    "dom_snippet": '<button data-action="lookup">Look up record</button>',
    "screenshot_path": str(directory / "failure.png"),
    "error_message": "Missing selector",
}
if case == "foreign":
    failure["workflow_id"] = "another-workflow"
if case != "missing":
    (directory / "failure_payload.json").write_text(json.dumps(failure))
print("selector failed", file=sys.stderr)
sys.exit(1)
