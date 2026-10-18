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
import json
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

from services.backend.config import Settings
from services.backend.main import create_app
from services.backend.tests.support import make_root
from services.backend.tests.test_real_runner import DEFINITION as PERMIT_DEFINITION
from services.backend.tests.test_real_runner import PARAMS as PERMIT_PARAMS
from services.backend.tests.test_real_runner import ROOT, VENV_PYTHON, free_port
from services.backend.tests.test_writes import RECORD_UPDATE

FIXTURES = ROOT / "services/backend/tests/fixtures"
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
        "runner": FIXTURES / "real_runner_shim.py", "runner_python": None,
        "wrong_output": lambda data: data.get("permit_id") != PERMIT_PARAMS["permit_id"],
    },
    "sandbox-hard": {
        "server": [sys.executable, str(ROOT / "services/backend/sandbox/records_site.py")], "path": "/records",
        "workflow": "record-update", "definition": RECORD_UPDATE, "params": SANDBOX_PARAMS,
        "chaos": {"enabled": True, "hard": True}, "field": "save_button",
        "runner": FIXTURES / "sandbox_runner.py", "runner_python": sys.executable,
        "wrong_output": lambda data: data != {"record_id": SANDBOX_PARAMS["record_id"], "value": SANDBOX_PARAMS["value"]},
    },
}


def trial(model, scenario, base_url, chrome):
    spec = SCENARIOS[scenario]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = json.loads((ROOT / f"contracts/selectors/{spec['workflow']}.json").read_text())
        baseline["target_url"] = f"{base_url}{spec['path']}"
        selectors_path = make_root(root, spec["workflow"], spec["definition"], baseline)
        env = {"SENTRY_DSN": "", "GEMINI_MODEL": model, "ANONYMIZED_TELEMETRY": "false",
               "MENDER_BROWSER_EXECUTABLE": chrome, "REAL_RUNNER_PYTHON": str(VENV_PYTHON),
               "REAL_PORTAL_URL": base_url, "REAL_RUNNER_SCRIPT": str(ROOT / "services/runner/execute.py"),
               "REAL_PLAYWRIGHT_BROWSERS": str(ROOT / ".venv/playwright-browsers")}
        kwargs = {"runner_python": spec["runner_python"]} if spec["runner_python"] else {}
        with patch.dict(os.environ, env):
            settings = Settings(root=root, runner_script=spec["runner"], runner_timeout=30,
                                browser_executable=chrome or None, **kwargs)
            with TestClient(create_app(settings)) as client:
                def post():
                    return client.post("/api/v1/run-workflow",
                                       json={"workflow": spec["workflow"], "params": spec["params"]}).json()

                if scenario == "sandbox-hard":
                    http(f"{base_url}/reset", {})
                http(f"{base_url}/chaos", spec["chaos"])
                started = time.perf_counter()
                heal = post()
                wall = time.perf_counter() - started
                if "status" not in heal:  # an HTTP error body, for example 503 or 422
                    heal = {"status": "error", "data": {}, "error": {"code": f"http_{heal.get('detail', 'error')}"[:60]}}
                selector = json.loads(selectors_path.read_text())["fields"][spec["field"]]
                after = post()
                after.setdefault("status", "error")
                landed = http(f"{base_url}/state")["records"] if scenario == "sandbox-hard" else None
                http(f"{base_url}/chaos", {"enabled": False})
            reports = list((root / "services/backend/state").glob("recovery-*.json"))
            report = json.loads(reports[0].read_text()) if reports else {"totals": {}, "attempts": []}
    totals = report.get("totals", {})
    committed = [r for r in heal.get("heal_records", []) if r["verification_outcome"] == "committed"]
    ok = (heal["status"] == "healed" and bool(committed) and after["status"] == "success"
          and not spec["wrong_output"](heal["data"]))
    if landed is not None:  # a write workflow must really have changed the site
        ok = ok and landed.get(SANDBOX_PARAMS["record_id"]) == SANDBOX_PARAMS["value"]
    return {"model": model, "scenario": scenario, "ok": ok, "status": heal["status"],
            "error": (heal.get("error") or {}).get("code"), "wall_s": round(wall, 1),
            "invocations": len(report.get("attempts", [])), "selector": selector if ok else None,
            "quality": selector_quality(selector) if ok else "none", "cost_usd": totals.get("cost_usd"),
            "cost_complete": totals.get("cost_usd_complete"), "prompt_tokens": totals.get("prompt_tokens"),
            "completion_tokens": totals.get("completion_tokens"), "total_tokens": totals.get("total_tokens")}


def summarize(rows):
    done = [r for r in rows if r["ok"]]
    costs = [r["cost_usd"] for r in rows if isinstance(r["cost_usd"], (int, float))]
    spend = sum(costs)
    return {"model": rows[0]["model"], "scenario": rows[0]["scenario"], "trials": len(rows), "success": len(done),
            "rate": round(len(done) / len(rows), 2),
            "mean_wall_s": round(statistics.mean(r["wall_s"] for r in rows), 1),
            "mean_cost_usd": round(spend / len(rows), 4) if costs else None,
            "cost_per_success_usd": round(spend / len(done), 4) if costs and done else None,
            "mean_tokens": round(statistics.mean(r["total_tokens"] for r in rows if r["total_tokens"])) if any(r["total_tokens"] for r in rows) else None,
            "qualities": sorted({r["quality"] for r in done}), "errors": sorted({r["error"] for r in rows if r["error"]})}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="comma separated model ids")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="permit")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--max-usd", type=float, default=4.0, help="stop when estimated spend reaches this")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    load_dotenv(ROOT / "services/backend/.env", override=False)
    chrome = os.getenv("MENDER_BROWSER_EXECUTABLE") or ""
    mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome = chrome or (mac_chrome if Path(mac_chrome).is_file() else "")
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen([*SCENARIOS[args.scenario]["server"], "--port", str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = args.out or ROOT / f"services/backend/state/model-bench-{args.scenario}-{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, spend, summaries = [], 0.0, []
    try:
        for _ in range(50):
            try:
                urlopen(f"{base_url}/healthz", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        for model in args.models.split(","):
            mine = []
            for number in range(1, args.trials + 1):
                if spend >= args.max_usd:
                    print(f"STOP: estimated spend ${spend:.2f} reached the cap", flush=True)
                    break
                row = trial(model, args.scenario, base_url, chrome)
                row["trial"] = number
                mine.append(row)
                rows.append(row)
                # An unknown cost still spent money, so count a conservative estimate toward the cap.
                spend += row["cost_usd"] if isinstance(row["cost_usd"], (int, float)) else UNKNOWN_COST_USD
                print(f"{model} #{number}: {'OK ' if row['ok'] else 'FAIL'} {row['wall_s']}s ${row['cost_usd']} "
                      f"{row['selector'] or row['error']} (spend ${spend:.3f})", flush=True)
                out.write_text(json.dumps({"rows": rows}, indent=2))
                if number >= 2 and not any(r["ok"] for r in mine) and all(r["error"] for r in mine):
                    print(f"{model}: failing outright, skipping its remaining trials", flush=True)
                    break
            if mine:
                summaries.append(summarize(mine))
                print("SUMMARY", json.dumps(summaries[-1]), flush=True)
            if spend >= args.max_usd:
                break
    finally:
        server.terminate()
        server.wait()
        out.write_text(json.dumps({"rows": rows, "summaries": summaries, "estimated_spend_usd": round(spend, 4)}, indent=2))
    print(f"Saved {out}; estimated spend ${spend:.3f}")


if __name__ == "__main__":
    main()
