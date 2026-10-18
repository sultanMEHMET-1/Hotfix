"""Demo rehearsal: python -m services.backend.rehearse [loops]. Needs the portal on :3000 and the backend on :8000.

Each loop resets, runs fast, enables Chaos Mode, heals with the paid agent, then runs fast again."""

import json
import sys
import time
from urllib.request import Request, urlopen
P = {"workflow": "permit-application", "params": {"permit_id": "PERMIT-2026-0042", "applicant_name": "Davis Municipal Works"}}
def call(url, body=None, timeout=300):
    req = Request(url, json.dumps(body).encode() if body is not None else None, {"content-type": "application/json"},
                  method="POST" if body is not None else "GET")
    return json.load(urlopen(req, timeout=timeout))
def run():
    t = time.perf_counter(); r = call("http://127.0.0.1:8000/api/v1/run-workflow", P); return r, time.perf_counter() - t

rows = []
for i in range(1, int(sys.argv[1] if len(sys.argv) > 1 else 5) + 1):
    call("http://127.0.0.1:3000/chaos", {"enabled": False})
    reset = call("http://127.0.0.1:8000/api/v1/admin/reset", {})
    fast, tf = run()
    call("http://127.0.0.1:3000/chaos", {"enabled": True})
    heal, th = run()
    after, ta = run()
    rec = [(r["verification_outcome"], r["version_before"], r.get("version_after")) for r in heal.get("heal_records", [])]
    ok = (fast["status"] == "success" and heal["status"] == "healed" and heal["data"] == {"status": "Approved", "inspector": "Davis"}
          and after["status"] == "success" and rec and all(x[0] == "committed" for x in rec))
    rows.append(ok)
    print(f"loop {i}: reset v{reset['version']} | fast {tf*1000:.0f} ms {fast['status']} | heal {th:.1f} s {heal['status']} "
          f"cost {heal.get('agent_cost_usd')} agent_ms {round(heal.get('agent_duration_ms') or 0)} {rec} diff {heal.get('diff')} "
          f"| after {ta*1000:.0f} ms {after['status']} | {'PASS' if ok else 'FAIL'}", flush=True)
print("RESULT", f"{sum(rows)}/{len(rows)} PASS")
