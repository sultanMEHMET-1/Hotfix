# Message for Person 1 (portal and runner)

Paste-ready. Everything below is already on `main` (PR #1).

---

Hi, the backend is merged into `main` and the whole chain now runs end to end: dashboard, backend,
your runner and portal, with a real Gemini heal. Five things you should know, then three asks.

**What I changed in your folders** (each is its own commit, so review or revert any of them):

1. `5ef594d` `services/runner/execute.py`: it now also accepts the backend's CLI,
   `--workflow <id> --params '<json>' --run-id <uuid>` (plus `--sentry-trace`, `--baggage`, accepted and
   ignored). With `--run-id` it writes `runs/<run_id>/failure_payload.json` and `failure.png` relative to
   the working directory. Your old flags still work and `test_execute.py` passes.
2. `50d580b` `contracts/selectors.json`: `target_url` is now `http://127.0.0.1:3000/permits/apply`
   (it was `portal.example.gov`, which made the backend reject every failure as `unexpected_page`).
   Only that field changed.
3. `40e8dbe` `services/portal/server.py` and `services/runner/execute.py`: the portal now puts the
   submitted permit id on the status badge (`data-permit`) and the runner returns it as `permit_id`.
   Before, the portal answered "Approved / Davis" for any input, so a wrong repair could not be caught
   by the canary. Output is now `{"status","inspector","permit_id"}`.
4. `40e8dbe` `services/runner/reset_demo.py`: it resets through the backend
   (`POST /api/v1/admin/reset`) when the backend is running, because the backend owns a lock on
   `selectors.json`. It only edits the file directly when no backend is listening.
5. Your two-second step timeouts, failure artifacts and chaos mutation all worked as designed. The
   randomized button class in the DOM snippet is fine: the backend ignores class attributes.

**Three asks**

1. **Read `target_url` from the selector map** in `execute.py` (`target_url = args.target_url or
   selector_map["target_url"]`). Today the runner has its own hard-coded copy of the same address, so
   there are two sources of truth.
2. **Generic runner (the big one).** Our goal is that any website can become a JSON endpoint. The runner
   is permit-specific today (four fixed fields, `--permit-id`). The backend already treats workflows
   generically: a definition lists ordered steps (input or click, with a role and label), a params schema,
   an output schema and a canary (see `services/backend/workflows/permit-application.json`). The runner
   should execute those steps against the CSS selectors in the selector map and return the output fields.
   A working example of a generic runner for another site is
   `services/backend/tests/fixtures/sandbox_runner.py`.
3. **Keep chaos mutations healable.** A repair only works if at least one unique CSS-addressable
   attribute survives on each changed element. Please do not randomize every attribute, and keep dynamic
   tokens or timestamps out of the failure DOM snippet (the 15 second failure cooldown matches repeat
   failures by that snippet).

Also: Public sites cannot be written to, so changing a value is only allowed on local or allow-listed
sites (`services/backend/sandbox/records_site.py` is a local site for that). Full details are in
`services/backend/HANDOFF.md`.
