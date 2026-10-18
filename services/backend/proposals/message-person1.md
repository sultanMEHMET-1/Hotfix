# Message for Person 1 (portal and runner)

Paste-ready. Everything below is on branch `codex/browser-use-recovery` (PR for review). The first part
is what changed in your folders; the asks from the earlier version of this message are done.

---

Hi, the whole chain runs end to end: dashboard, backend, your runner and portal, with a real Gemini heal.
Because you wanted any site to become an endpoint, I made your runner generic. Each change is its own
commit, so review or revert any of them.

**What changed in your folders**

1. `services/runner/execute.py` is generic. `--workflow <id>` reads `contracts/workflows/<id>.json`
   (ordered steps, how each output is read) and `contracts/selectors/<id>.json` (page URL and CSS
   selectors), opens the map's `target_url`, runs the steps, reads the outputs and prints one JSON object.
   No site-specific code. Your old flags (`--permit-id`, `--applicant-name`) and `test_execute.py` still
   work. `--run-id` writes `runs/<run_id>/failure_payload.json` and `failure.png`; it prints
   `runner_timings_ms={...}` on stderr, which the backend shows in Sentry. Your two-second timeouts and
   failure artifacts are unchanged.
2. The portal puts the submitted permit id on the status badge (`data-permit`) and the runner returns it
   as `permit_id`, so the canary can tell a wrong repair from a right one.
3. `services/runner/reset_demo.py` resets through the backend (`POST /api/v1/admin/reset`) when it is
   running, because the backend locks the maps. It edits the file itself only when no backend is listening.
4. `contracts/selectors.json` is now `contracts/selectors/permit-application.json`, with the real
   `target_url`. A second site, `record-update`, lives next to it; the local site that goes with it is
   `services/backend/sandbox/records_site.py`.

**One ask that still stands**

Keep chaos mutations healable. A repair only works if at least one unique CSS-addressable attribute
survives on each changed element, so please do not randomize every attribute. Keep dynamic tokens and
timestamps out of the failure DOM snippet (the 15 second failure cooldown matches repeat failures by
that snippet; the randomized button class is fine, the backend ignores class attributes).

Also: public sites cannot be written to, so a workflow that changes a value (`"mutates": true`) runs only
on local or allow-listed sites. Full details are in `services/backend/HANDOFF.md`.
