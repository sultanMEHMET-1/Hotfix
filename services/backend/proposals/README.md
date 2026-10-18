# Proposals for other owners

Authored by the backend owner, not applied. Each patch was applied to a scratch copy of
this branch and verified with the full stack (real portal, real runner, backend served
by uvicorn, real Gemini): `python -m services.backend.rehearse 5` passed 5 of 5 loops.

| Patch | For | What it fixes |
| --- | --- | --- |
| `runner-backend-cli.patch` | Person 1 (`services/runner/execute.py`) | Adds the agreed `--workflow --params --run-id` (plus accepted `--sentry-trace`, `--baggage`). With `--run-id` it writes `runs/<run_id>/failure_payload.json` and `failure.png`. Old flags still work and `services/runner/test_execute.py` still passes. |
| `contracts-target-url.patch` | Contracts owner (`contracts/selectors.json`) | `target_url` is `portal.example.gov`, but the portal is at `127.0.0.1:3000`. The backend rejects failures from another origin as `unexpected_page`, so recovery cannot start until this matches. |

Apply from the repository root: `git apply services/backend/proposals/<name>.patch`.

Not patched, only recommended:

- `services/runner/reset_demo.py` edits `selectors.json` with no lock. Use
  `POST /api/v1/admin/reset` (loopback only) instead, or run it with the backend stopped.
- The portal returns Approved / Davis for any input, so a canary cannot catch a
  wrong-record heal. Echoing the submitted permit id in the result would fix that.
