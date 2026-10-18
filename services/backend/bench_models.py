"""Compare Gemini models on the real heal task. PAID: every trial is a real agent run.

Each trial: fresh selector map, Chaos Mode on, one request through the real backend (real
Gemini, real Playwright replay, real canary), then a second request that must succeed on the
healed selector. Run from the repository root with the live requirements and the project venv:

  MENDER_REAL_RUNNER=1 uv run --no-project --python 3.12 \\
    --with-requirements services/backend/requirements-live.txt \\
    python -B -m services.backend.bench_models --models gemini-2.5-flash,gemini-3.8-flash --trials 5

Cost comes from the Browser Use SDK's pricing table (an estimate, not a bill).
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time
from unittest.mock import patch
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from services.backend.config import Settings
from services.backend.main import create_app
from services.backend.tests.test_real_runner import DEFINITION, PARAMS, ROOT, VENV_PYTHON, free_port

UNKNOWN_COST_USD = 0.15  # counted toward --max-usd when a trial reports no reliable cost
SHIM = ROOT / "services/backend/tests/fixtures/real_runner_shim.py"
STABLE = ("data-action", "data-testid", "aria-label", "[id", "#")  # attribute or id based
FRAGILE = ("nth-", ">", ":first", ":last")


def selector_quality(selector):
    if not selector:
        return "none"
    if any(token in selector for token in FRAGILE):
        return "structural"
    return "attribute" if any(token in selector for token in STABLE) else "other"


def trial(model, portal, chrome):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copytree(ROOT / "contracts", root / "contracts")
        (root / "services/backend/workflows").mkdir(parents=True)
        (root / "services/backend/workflows/permit-application.json").write_text(json.dumps(DEFINITION))
        baseline = json.loads((ROOT / "contracts/selectors.json").read_text())
        baseline["target_url"] = f"{portal}/permits/apply"
        (root / "contracts/selectors.json").write_text(json.dumps(baseline))
        env = {"SENTRY_DSN": "", "GEMINI_MODEL": model, "ANONYMIZED_TELEMETRY": "false",
               "MENDER_BROWSER_EXECUTABLE": chrome, "REAL_RUNNER_PYTHON": str(VENV_PYTHON),
               "REAL_PORTAL_URL": portal, "REAL_RUNNER_SCRIPT": str(ROOT / "services/runner/execute.py"),
               "REAL_PLAYWRIGHT_BROWSERS": str(ROOT / ".venv/playwright-browsers")}
        with patch.dict(os.environ, env):
            settings = Settings(root=root, runner_script=SHIM, runner_timeout=30, browser_executable=chrome or None)
            with TestClient(create_app(settings)) as client:
                def post():
                    return client.post("/api/v1/run-workflow", json={"workflow": "permit-application", "params": PARAMS}).json()

                urlopen(Request(f"{portal}/chaos", b'{"enabled": true}', {"content-type": "application/json"}, method="POST"), timeout=3).read()
                started = time.perf_counter()
                heal = post()
                wall = time.perf_counter() - started
                if "status" not in heal:  # an HTTP error body, for example 503 or 422
                    heal = {"status": "error", "data": {}, "error": {"code": f"http_{heal.get('detail', 'error')}"[:60]}}
                selector = json.loads((root / "contracts/selectors.json").read_text())["fields"]["submit_button"]
                after = post()
                after.setdefault("status", "error")
                urlopen(Request(f"{portal}/chaos", b'{"enabled": false}', {"content-type": "application/json"}, method="POST"), timeout=3).read()
            reports = list((root / "services/backend/state").glob("recovery-*.json"))
            report = json.loads(reports[0].read_text()) if reports else {"totals": {}, "attempts": []}
    totals = report.get("totals", {})
    committed = [r for r in heal.get("heal_records", []) if r["verification_outcome"] == "committed"]
    ok = (heal["status"] == "healed" and bool(committed) and after["status"] == "success"
          and heal["data"].get("permit_id") == PARAMS["permit_id"])
    return {"model": model, "ok": ok, "status": heal["status"], "error": (heal.get("error") or {}).get("code"),
            "wall_s": round(wall, 1), "invocations": len(report.get("attempts", [])), "selector": selector if ok else None,
            "quality": selector_quality(selector) if ok else "none", "cost_usd": totals.get("cost_usd"),
            "cost_complete": totals.get("cost_usd_complete"), "prompt_tokens": totals.get("prompt_tokens"),
            "completion_tokens": totals.get("completion_tokens"), "total_tokens": totals.get("total_tokens")}


def summarize(rows):
    done = [r for r in rows if r["ok"]]
    costs = [r["cost_usd"] for r in rows if isinstance(r["cost_usd"], (int, float))]
    spend = sum(costs)
    return {"model": rows[0]["model"], "trials": len(rows), "success": len(done),
            "rate": round(len(done) / len(rows), 2),
            "mean_wall_s": round(statistics.mean(r["wall_s"] for r in rows), 1),
            "mean_cost_usd": round(spend / len(rows), 4) if costs else None,
            "cost_per_success_usd": round(spend / len(done), 4) if costs and done else None,
            "mean_tokens": round(statistics.mean(r["total_tokens"] for r in rows if r["total_tokens"])) if any(r["total_tokens"] for r in rows) else None,
            "qualities": sorted({r["quality"] for r in done}), "errors": sorted({r["error"] for r in rows if r["error"]})}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="comma separated model ids")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--max-usd", type=float, default=4.0, help="stop when estimated spend reaches this")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    load_dotenv(ROOT / "services/backend/.env", override=False)
    chrome = os.getenv("MENDER_BROWSER_EXECUTABLE") or ""
    mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome = chrome or (mac_chrome if Path(mac_chrome).is_file() else "")
    port = free_port()
    portal_url = f"http://127.0.0.1:{port}"
    portal = subprocess.Popen([str(VENV_PYTHON), str(ROOT / "services/portal/server.py"), "--port", str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = args.out or ROOT / f"services/backend/state/model-bench-{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, spend, summaries = [], 0.0, []
    try:
        for _ in range(50):
            try:
                urlopen(f"{portal_url}/healthz", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        for model in args.models.split(","):
            mine = []
            for number in range(1, args.trials + 1):
                if spend >= args.max_usd:
                    print(f"STOP: estimated spend ${spend:.2f} reached the cap", flush=True)
                    break
                row = trial(model, portal_url, chrome)
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
        portal.terminate()
        portal.wait()
        out.write_text(json.dumps({"rows": rows, "summaries": summaries, "estimated_spend_usd": round(spend, 4)}, indent=2))
    print(f"Saved {out}; estimated spend ${spend:.3f}")


if __name__ == "__main__":
    main()
