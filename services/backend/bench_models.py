"""Compare Gemini models on a real heal task. PAID: every trial is a real agent run.

Scenarios:
  permit        the demo: Chaos Mode breaks the permit portal's submit button (real runner, real portal)
  sandbox-hard  the local record editor with Chaos Mode plus decoys (a search box, "Save draft" and
                "Clear form" buttons) that a weak agent could use by mistake; the write must also land

Each trial: fresh selector map, Chaos Mode on, one request through the real backend (real Gemini,
real Playwright replay, real canary), then a second request that must succeed on the healed selector.
Run from the repository root with the live requirements and the project venv:

  MENDER_REAL_RUNNER=1 uv run --no-project --python 3.12 \\
    --with-requirements services/backend/requirements-live.txt \\
    python -B -m services.backend.bench_models --models gemini-3.5-flash-lite --trials 5

Cost comes from the Browser Use SDK's pricing table (an estimate, not a bill; thinking tokens count
as output). A trial with no reliable cost counts a conservative estimate toward --max-usd.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from services.backend.config import BackendError, Settings
from services.backend.main import create_app
from services.backend.tests.support import make_root
from services.backend.tests.test_real_runner import DEFINITION as PERMIT_DEFINITION
from services.backend.tests.test_real_runner import PARAMS as PERMIT_PARAMS
from services.backend.tests.test_real_runner import ROOT, VENV_PYTHON, free_port
from services.backend.tests.test_writes import RECORD_UPDATE

RUNNER = ROOT / "services/runner/execute.py"
UNKNOWN_COST_USD = 0.15  # counted toward --max-usd when a trial reports no reliable cost
STABLE = ("data-action", "data-testid", "aria-label", "[id", "#")  # attribute or id based
FRAGILE = ("nth-", ">", ":first", ":last")
SANDBOX_PARAMS = {"record_id": "bench-record", "value": "bench-value"}


def selector_quality(selector):
    if not selector:
        return "none"
    if any(token in selector for token in FRAGILE):
        return "structural"
    return "attribute" if any(token in selector for token in STABLE) else "other"


def http(url, body=None):
    request = Request(url, json.dumps(body).encode() if body is not None else None,
                      {"content-type": "application/json"}, method="POST" if body is not None else "GET")
    return json.load(urlopen(request, timeout=5))


SCENARIOS = {
    "permit": {
        "server": [str(VENV_PYTHON), str(ROOT / "services/portal/server.py")], "path": "/permits/apply",
        "workflow": "permit-application", "definition": PERMIT_DEFINITION, "params": PERMIT_PARAMS,
        "chaos": {"enabled": True}, "field": "submit_button",
        "runner": RUNNER,
        "wrong_output": lambda data: data.get("permit_id") != PERMIT_PARAMS["permit_id"],
    },
    "sandbox-hard": {
        "server": [sys.executable, str(ROOT / "services/backend/sandbox/records_site.py")], "path": "/records",
        "workflow": "record-update", "definition": RECORD_UPDATE, "params": SANDBOX_PARAMS,
        "chaos": {"enabled": True, "hard": True}, "field": "save_button",
        "runner": RUNNER,
        "wrong_output": lambda data: data != {"record_id": SANDBOX_PARAMS["record_id"], "value": SANDBOX_PARAMS["value"]},
    },
}


def sandbox_checks(initial, saved, expanded):
    expected = {**initial["records"], SANDBOX_PARAMS["record_id"]: SANDBOX_PARAMS["value"],
                RECORD_UPDATE["canary"]["params"]["record_id"]: RECORD_UPDATE["canary"]["params"]["value"]}
    checks = {"landed_values": saved["records"] == expected, "write_limit": 0 < saved["writes"] <= 3}
    if expanded:
        audit = saved.get("audit")
        allowed = {SANDBOX_PARAMS["record_id"], RECORD_UPDATE["canary"]["params"]["record_id"]}
        checks.update(note_untouched="supplier_note" in saved and saved["supplier_note"] is None,
                      audit_bound=isinstance(audit, list) and len(audit) == min(saved["writes"], 5),
                      audit_price_only=isinstance(audit, list) and all(
                          entry["record_id"] in allowed and entry["new_value"] == expected[entry["record_id"]] for entry in audit))
    return checks


async def refuse_followup_diagnosis(*args, **kwargs):
    raise BackendError("unexpected_recovery", "The benchmark follow-up must remain deterministic")


def trial(model, scenario, base_url, chrome, *, condition="candidate"):
    spec = SCENARIOS[scenario]
    before_followup = after_followup = initial = None
    followup_wall = None
    checks = {}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = json.loads((ROOT / f"contracts/selectors/{spec['workflow']}.json").read_text())
        baseline["target_url"] = f"{base_url}{spec['path']}"
        selectors_path = make_root(root, spec["workflow"], spec["definition"], baseline)
        env = {"SENTRY_DSN": "", "GEMINI_MODEL": model, "ANONYMIZED_TELEMETRY": "false",
               "MENDER_BROWSER_EXECUTABLE": chrome}
        with patch.dict(os.environ, env):
            settings = Settings(root=root, runner_script=RUNNER, runner_python=str(VENV_PYTHON), runner_timeout=30,
                                browser_executable=chrome or None)
            with TestClient(create_app(settings)) as client:
                def post():
                    return client.post("/api/v1/run-workflow",
                                       json={"workflow": spec["workflow"], "params": spec["params"]}).json()

                if scenario == "sandbox-hard":
                    http(f"{base_url}/reset", {})
                    initial = http(f"{base_url}/state")
                http(f"{base_url}/chaos", spec["chaos"])
                started = time.perf_counter()
                heal = post()
                wall = time.perf_counter() - started
                if "status" not in heal:
                    heal = {"status": "error", "data": {}, "error": {"code": f"http_{heal.get('detail', 'error')}"[:60]}}
                selector = json.loads(selectors_path.read_text())["fields"][spec["field"]]
                reports = list((root / "services/backend/state").glob("recovery-*.json"))
                report = json.loads(reports[0].read_text()) if reports else {"totals": {}, "attempts": []}
                if initial is not None:
                    before_followup = http(f"{base_url}/state")
                    checks = sandbox_checks(initial, before_followup, condition == "candidate")
                after = {"status": "not_run"}
                if heal["status"] == "healed":
                    client.app.state.diagnose = refuse_followup_diagnosis
                    followup_started = time.perf_counter()
                    after = post()
                    followup_wall = round(time.perf_counter() - followup_started, 3)
                    after.setdefault("status", "error")
                    checks["deterministic_followup"] = after["status"] == "success" and not after.get("recovery_attempted", False)
                    checks["followup_output"] = not spec["wrong_output"](after.get("data", {}))
                    if initial is not None:
                        after_followup = http(f"{base_url}/state")
                        checks["followup_write"] = after_followup["writes"] == before_followup["writes"] + 1
                        checks["followup_values"] = after_followup["records"] == before_followup["records"]
                        if condition == "candidate":
                            checks["followup_note"] = after_followup.get("supplier_note", "missing") is None
                            checks["followup_audit_bound"] = len(after_followup.get("audit", [])) == min(after_followup["writes"], 5)
                http(f"{base_url}/chaos", {"enabled": False})
    totals = report.get("totals", {})
    committed = [r for r in heal.get("heal_records", []) if r["verification_outcome"] == "committed"]
    ok = (heal["status"] == "healed" and bool(committed) and after["status"] == "success"
          and not spec["wrong_output"](heal["data"]) and all(checks.values()))
    return {"model": model, "scenario": scenario, "condition": condition, "ok": ok, "status": heal["status"],
            "error": (heal.get("error") or {}).get("code"), "wall_s": round(wall, 3),
            "invocations": len(report.get("attempts", [])), "selector": selector,
            "quality": selector_quality(selector), "cost_usd": totals.get("cost_usd"),
            "cost_complete": totals.get("cost_usd_complete"), "prompt_tokens": totals.get("prompt_tokens"),
            "completion_tokens": totals.get("completion_tokens"), "total_tokens": totals.get("total_tokens"),
            "heal_records": heal.get("heal_records", []), "output": heal.get("data"),
            "followup": after, "followup_wall_s": followup_wall,
            "site_checks": checks, "before_followup": before_followup, "after_followup": after_followup}


def valid_cost(cost):
    return type(cost) in (int, float) and math.isfinite(cost) and cost >= 0


def budget_cost(row):
    cost = row.get("cost_usd")
    numeric = valid_cost(cost)
    return cost if numeric and row.get("cost_complete") is True else max(cost if numeric else 0, UNKNOWN_COST_USD)


def summarize(rows):
    done = [r for r in rows if r["ok"]]
    complete = all(valid_cost(r["cost_usd"]) and r.get("cost_complete") is True for r in rows)
    spend = sum(r["cost_usd"] for r in rows) if complete else None
    return {"model": rows[0]["model"], "scenario": rows[0]["scenario"], "condition": rows[0].get("condition", "candidate"),
            "trials": len(rows), "success": len(done), "rate": round(len(done) / len(rows), 2),
            "mean_wall_s": statistics.mean(r["wall_s"] for r in rows),
            "range_wall_s": [min(r["wall_s"] for r in rows), max(r["wall_s"] for r in rows)],
            "mean_cost_usd": spend / len(rows) if complete else None,
            "cost_per_success_usd": spend / len(done) if complete and done else None,
            "mean_tokens": round(statistics.mean(r["total_tokens"] for r in rows if r["total_tokens"])) if any(r["total_tokens"] for r in rows) else None,
            "qualities": sorted({r["quality"] for r in done}), "errors": sorted({r["error"] for r in rows if r["error"]})}


def paired_schedule():
    return [("baseline", 1), ("candidate", 1), ("candidate", 2), ("baseline", 2), ("baseline", 3), ("candidate", 3)]


def comparison(rows):
    summaries = {condition: summarize([row for row in rows if row["condition"] == condition])
                 for condition in ("baseline", "candidate") if any(row["condition"] == condition for row in rows)}
    complete = all(summaries.get(condition, {}).get("trials") == 3 for condition in ("baseline", "candidate"))
    baseline, candidate = summaries.get("baseline", {}), summaries.get("candidate", {})
    measured = complete and candidate.get("mean_cost_usd") is not None
    passed = measured and candidate["success"] == 3 and candidate["mean_wall_s"] <= 20 and candidate["mean_cost_usd"] <= 0.01
    return {"complete": complete, "candidate_passed": bool(passed), "summaries": summaries,
            "time_ratio": candidate["mean_wall_s"] / baseline["mean_wall_s"] if complete and baseline["mean_wall_s"] else None,
            "cost_ratio": candidate["mean_cost_usd"] / baseline["mean_cost_usd"] if complete and candidate.get("mean_cost_usd") is not None and baseline.get("mean_cost_usd") else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="comma separated model ids")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="permit")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--max-usd", type=float, default=4.0, help="stop when conservative spend reaches this, checked between trials")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--baseline-site", type=Path, help="paired sandbox-hard comparison with this pinned site's script")
    args = parser.parse_args()
    if args.trials < 1 or args.max_usd <= 0:
        parser.error("trials and max-usd must be positive")
    if args.baseline_site and (args.scenario != "sandbox-hard" or args.trials != 3 or "," in args.models or not args.baseline_site.is_file()):
        parser.error("baseline-site requires sandbox-hard, one model, three pairs and an existing site script")
    load_dotenv(ROOT / "services/backend/.env", override=False)
    chrome = os.getenv("MENDER_BROWSER_EXECUTABLE") or ""
    mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome = chrome or (mac_chrome if Path(mac_chrome).is_file() else "")
    out = args.out or ROOT / f"services/backend/state/model-bench-{args.scenario}-{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, servers, urls, spend = [], [], {}, 0.0
    sources = {"candidate": SCENARIOS[args.scenario]["server"]}
    if args.baseline_site:
        sources["baseline"] = [sys.executable, str(args.baseline_site.resolve())]
    metadata = {"site_sha256": {condition: hashlib.sha256(Path(command[1]).read_bytes()).hexdigest() for condition, command in sources.items()}}

    def save_results():
        summaries = [summarize([r for r in rows if r["model"] == model and r["condition"] == condition])
                     for model in args.models.split(",") for condition in sources
                     if any(r["model"] == model and r["condition"] == condition for r in rows)]
        result = {**metadata, "rows": rows, "summaries": summaries, "estimated_spend_usd": spend}
        if args.baseline_site:
            result["comparison"] = comparison(rows)
        out.write_text(json.dumps(result, indent=2))

    try:
        for condition, command in sources.items():
            port = free_port()
            urls[condition] = f"http://127.0.0.1:{port}"
            servers.append(subprocess.Popen([*command, "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            for _ in range(50):
                try:
                    http(f"{urls[condition]}/healthz")
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"{condition} site did not start")
        for model in args.models.split(","):
            schedule = paired_schedule() if args.baseline_site else [("candidate", number) for number in range(1, args.trials + 1)]
            for condition, number in schedule:
                if spend >= args.max_usd:
                    print(f"STOP: conservative spend ${spend:.3f} reached the cap", flush=True)
                    break
                started = time.perf_counter()
                try:
                    row = trial(model, args.scenario, urls[condition], chrome, condition=condition)
                except Exception as exc:
                    row = {"model": model, "scenario": args.scenario, "condition": condition,
                           "ok": False, "status": "error", "error": f"trial_exception:{type(exc).__name__}",
                           "wall_s": round(time.perf_counter() - started, 3), "selector": None,
                           "quality": "none", "cost_usd": None, "cost_complete": False, "total_tokens": None}
                row["trial"] = number
                rows.append(row)
                spend += budget_cost(row)
                save_results()
                print(f"{condition} {model} #{number}: {'OK' if row['ok'] else 'FAIL'} {row['wall_s']:.1f}s "
                      f"${row['cost_usd']} {row['selector']} (spend ${spend:.3f})", flush=True)
            if spend >= args.max_usd:
                break
    finally:
        for server in servers:
            server.terminate()
        for server in servers:
            server.wait()
        save_results()
    if args.baseline_site:
        print("COMPARISON", json.dumps(comparison(rows)), flush=True)
    print(f"Saved {out}; conservative spend ${spend:.3f}")


if __name__ == "__main__":
    main()
