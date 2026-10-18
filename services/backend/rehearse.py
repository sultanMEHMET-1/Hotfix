"""Demo rehearsal over the API. Paid: one Gemini heal per loop.

  python -m services.backend.rehearse [loops]

Needs the portal on :3000 and the backend on :8000 (with MENDER_RUNNER_PYTHON pointing at the
project venv). Each loop resets, runs the fast path, enables Chaos Mode, heals with the agent, and runs
the fast path again. Exits 1 if any loop fails.
"""

import json
import sys
import time
from urllib.request import Request, urlopen

BACKEND = "http://127.0.0.1:8000"
PORTAL = "http://127.0.0.1:3000"
REQUEST = {"workflow": "permit-application",
           "params": {"permit_id": "PERMIT-2026-0042", "applicant_name": "Davis Municipal Works"}}


def call(url, body=None, timeout=300):
    request = Request(url, json.dumps(body).encode() if body is not None else None,
                      {"content-type": "application/json"}, method="POST" if body is not None else "GET")
    return json.load(urlopen(request, timeout=timeout))


def run():
    started = time.perf_counter()
    response = call(f"{BACKEND}/api/v1/run-workflow", REQUEST)
    return response, time.perf_counter() - started


def main():
    loops = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    expected = {"status": "Approved", "inspector": "Davis", "permit_id": REQUEST["params"]["permit_id"]}
    passed = 0
    for loop in range(1, loops + 1):
        call(f"{PORTAL}/chaos", {"enabled": False})
        reset = call(f"{BACKEND}/api/v1/admin/reset", {})
        fast, fast_s = run()
        call(f"{PORTAL}/chaos", {"enabled": True})
        heal, heal_s = run()
        after, after_s = run()
        records = [(r["verification_outcome"], r["version_before"], r.get("version_after"))
                   for r in heal.get("heal_records", [])]
        ok = bool(fast["status"] == "success" and heal["status"] == "healed" and heal["data"] == expected
                  and after["status"] == "success" and records and all(r[0] == "committed" for r in records))
        passed += ok
        print(f"loop {loop}: reset v{reset['version']} | fast {fast_s * 1000:.0f} ms {fast['status']} | "
              f"heal {heal_s:.1f} s {heal['status']} cost {heal.get('agent_cost_usd')} "
              f"agent_ms {round(heal.get('agent_duration_ms') or 0)} {records} diff {heal.get('diff')} | "
              f"after {after_s * 1000:.0f} ms {after['status']} | {'PASS' if ok else 'FAIL'}", flush=True)
    print(f"RESULT {passed}/{loops} PASS")
    sys.exit(0 if passed == loops else 1)


if __name__ == "__main__":
    main()
