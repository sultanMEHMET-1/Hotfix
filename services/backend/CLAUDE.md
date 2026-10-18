# Mender: context for Claude Code

## What this is
Mender is a hackathon project (LA Hacks, AI track, 24 hours, software only). It turns an API-less web portal into a fast JSON endpoint that repairs itself when the site changes.
- A deterministic Playwright runner drives a mock legacy portal using CSS selectors from contracts/selectors/<workflow>.json. No LLM on the fast path. Any workflow in contracts/workflows/ runs the same way.
- When the portal changes (Chaos Mode) a selector breaks and the runner fails with a failure artifact.
- The backend catches that, spawns a Browser Use agent (Gemini) to complete the workflow on the changed page, derives a CSS selector for the broken field from the recorded history, verifies it by replaying the runner, patches the selector map, and returns the result.
- Sentry (tracing, logs, AI agent monitoring, profiling, and Session Replay on the dashboard) wraps everything. It is a judged prize track, so Sentry must be load-bearing, not decoration.

## Who owns what
- Person 1: /services/portal and /services/runner. Person 3: /services/dashboard. Person 2 (the user, who you work for): /services/backend. /contracts holds shared interfaces.
- Default: author code only under /services/backend. Runtime updates of the selector maps (including version bump) by the healer are always allowed. The user has authorized cross-owner changes for the current branch ("fix everything first", then "if we need to change the contracts do so, change whatever you'd like in the codebase"): the generic runner, contracts layout, dashboard picker and Sentry. Those are in their own commits as separate commits. For anything beyond this branch's scope, ask again.
- Branch: codex/browser-use-recovery. Push only to it. Never merge to main without a fresh explicit instruction. (PR #1 was merged into main at the user's explicit instruction, merge commit a09569c; that was a one-time authorization.)

## Prize tracks the demo must support
Sentry (Best Use of Sentry), Browser Use, MLH Best Use of Gemini API. Cognition/Devin PR step is a stretch goal, not built. The demo: run a lookup (fast, about 300 ms, no LLM), click Chaos Mode on the mock portal, rerun, watch the dashboard switch to "Browser Use Agent Engaged", get correct JSON back, then show the Sentry trace, agent spans and the selector diff. It must be repeatable five times in a row. Prefer simple and deterministic over clever.

## Architecture decisions (settled, do not relitigate)
- Runner CLI is site-agnostic: python services/runner/execute.py --workflow <id> --params '<json>' --run-id <uuid> --contracts <root>/contracts (optional --sentry-trace, --baggage). Success: exit 0, one JSON object. Failure: non-zero exit, runs/<run_id>/failure_payload.json and failure.png. Endpoint: POST /api/v1/run-workflow with {"workflow": "...", "params": {...}}. No permit-specific code in the backend.
- Each workflow has a definition in contracts/workflows/<id>.json (the only place): goal, ordered steps (inputs name their param), outputs (field + text or attr:name), params_schema, output_schema, a required canary (volatile paths may be excluded), optional mutates. Its selector map is contracts/selectors/<id>.json (target_url, version, fields). The ordered steps are authoritative for execution order; field order in the map means nothing.
- Selectors are CSS. Browser Use history gives attributes, XPath and node identity, not trusted CSS, so derive candidates and prove uniqueness on the live page. Runner replay is the real verification. Never accept a selector because the agent produced it.
- Browser Use 0.13.11 with Gemini (ChatGoogle), imported lazily and off the event loop. The fast path never imports it.
- Transactional recovery: baseline snapshot, one failed field patched per attempt, provisional patches kept only while replay shows forward progress (failure at a later ordered step), commit only after full replay, output schema validation and the canary pass. Otherwise restore the baseline as a NEW higher version, never reuse a version. A broken read (the selector that reads the answer) is repaired too: the agent reports the visible values, the backend finds the one element showing them, and the replay must read them back before the canary decides. Max 3 agent invocations, one monotonic 240 s deadline (stop work at 210 s, last 30 s reserved for cleanup). Replay and canary run under the already-held exclusive lock without reacquiring it. One lock and one store per workflow. An in-flight marker (state/inflight-<wf>.json) lets startup roll back a recovery that a crash interrupted.
- Recovery runs as a shielded background task per workflow that waiters join. A client disconnect must not cancel it. One Uvicorn worker. Agent errors, timeouts, no-result and agent_blocked may retry the same field within the 3 cap. agent_blocked is retryable on purpose (measured: it fixed two models quitting early on normal pages), so a real login wall costs up to three runs before it fails; that is the accepted tradeoff. Ambiguous evidence and invalid candidates abort.
- Failure cooldown: one completed failure per workflow is kept in memory for 15 s after cleanup. The key is workflow, failed step, old selector, the full selector map (taken after cleanup, since rollback bumps the version) and a hash of the failure artifact. Cache hits never extend expiry. Never cache config errors, failures without valid runner evidence, cancellations, or failed cleanup or restoration.
- Response: heal_records, error, agent_cost_usd, agent_duration_ms are approved and enabled. Failures are HTTP 200 with status="failed", healed=false, data={}, structured error, no top-level diff. Cost and agent duration appear only on the request that started recovery, only when reliable, never 0 for unknown. error.message must be safe to show (no keys, paths, raw prompts, stack traces). heal_records describe the selector transaction; status describes the caller's own run.
- Creation from a sentence (author.py): read-only, four allowlisted sites with fixed start URLs, action words refused before any model call, a pre-action veto (typing and clicking only; no text areas, password fields, or edit, publish or login controls), a replay on two different inputs before anything is kept, quotas (one at a time, 5 attempts per hour, 20 kept), loopback only. Created workflows are `custom-*` local files ignored by git.
- Scope: reads work on any reachable site; workflows that change data (`"mutates": true`) run only on loopback or `MENDER_WRITE_HOSTS` hosts, enforced in main.py. Login or captcha walls are never bypassed (agent_blocked). Write demos use sandbox/records_site.py.
- Reset for demo rehearsals: POST /api/v1/admin/reset (loopback only) restores selectors from git HEAD as a new version and clears the cooldown; body {workflow?} resets one workflow or all. GET /api/v1/workflows lists the workflows. GET /api/v1/status shows why the backend is blocked.

## Coding rules
- Validate against the contract schemas (jsonschema and the shared Pydantic models). If a contract is wrong or missing something, stop and tell the user.
- Secrets and model names come from environment variables, never hard-coded or committed.
- No em dashes anywhere (code, comments, docs, messages). Emoji-free logs.
- Check installed package versions and their docs instead of relying on memory (Sentry, Browser Use and Gemini SDKs change fast).
- Mock the agent in unit tests. Paid Gemini calls are opt-in tests only.
- Use the rigorous-coding, adversarial-verification and deliberate-thinking skills when available. If not, apply the same discipline.

## Working agreement (so the user does not have to relay between agents)
1. **Plan, then self-audit, then present.** For each milestone, write the plan, then audit it yourself before showing anything. If you can spawn a subagent, use a fresh reviewer that has not seen your reasoning and gets only the plan, the contracts and the checklist below. Fix what it finds. Present a single final plan with a short list of decisions that genuinely need the user.
2. **Decide, don't ask, when there is a conventional default.** Ask only when the choice touches a contract, another person's folder, or a demo-visible tradeoff. Ask in one batch, with your recommendation first.
3. **Implement, verify, then stop** at each milestone boundary with exact test results, live measurements and remaining limitations. Do not start the next milestone unasked.
4. **Keep the handoff current.** Update the backend run guide (README.md) and agent handoff file (HANDOFF.md) at each milestone so a fresh session (or another agent) can resume from the repo alone. Commit small and often on the feature branch.
5. Scope discipline: no Redis, database, retry endpoint, persistent cooldown, dashboard work, real portal integration, persistent crash-recovery beyond the marker, or automatic PR generation unless the user says so.

## Audit checklist (the issues earlier reviews actually found)
- Does a contract conflict hide in the plan (response fields, selector shape, versions)?
- Rollback: can it undo a correct repair, reuse a version number, or leave a candidate installed after timeout or cancellation?
- Locks: any deadlock from re-entrancy, or fast-path requests waiting with no bound?
- Duplicate work: do concurrent requests each launch their own agent run?
- Cancellation: does a client disconnect kill a recovery that was about to succeed?
- Cache or cooldown keys too loose (a different failure returning a stale result)?
- Cost leakage: cost shown to waiters, double-counted, or reported as 0 when unknown?
- Timeouts: does the runner's per-step timeout (about 2 s) keep fast-path failure detection quick, and does the monotonic deadline cover imports, locks, replay, canary and cleanup?
- Silent wrongness: a schema-valid but wrong heal when no canary exists. Can the agent's element be mapped to the wrong step?
- Error text leaking secrets, paths, prompts or stack traces?
- Hackathon realism: will this run repeatedly on conference Wi-Fi, and is it too complex for the time left?

## Dependencies on teammates (flag, do not work around)
- Person 1: the generic runner and map-driven target_url are done. Keep per-step Playwright timeouts at about 2 s; keep chaos mutations healable (at least one unique CSS-addressable attribute per changed element); keep dynamic tokens and timestamps out of the failure DOM snippet, or the 15 s cooldown never hits. A paste-ready message is in `proposals/message-person1.md`.
- Person 3: the dashboard has the workflow picker, the cooldown countdown (cooldown_remaining_s), honest n/a numbers, accumulating corrections, the create-from-a-sentence panel and Sentry browser tracing and Replay. Remember that heal_records describe the selector transaction while status describes the caller's run.
- Contracts: the team owns them together, so contract changes need no outside review. Decided: agent_duration_ms is the sum of SDK step durations, and empty heal_records are omitted rather than sent as [].

## Commands
Run from the repository root with Python 3.12 and uv. Full lists and costs are in README.md ("Tests and tools").
- Default tests (mocked agent, no paid calls): `uv run --no-project --python 3.12 --with-requirements services/backend/requirements-test.txt python -B -m unittest discover -s services/backend/tests`
- Dashboard: `cd services/dashboard && npm run typecheck && npm test`. Runner: `cd services/runner && ../../.venv/bin/python -m unittest test_execute`.
- Paid, browser and network tests are opt-in (`MENDER_LIVE_TEST=1`, `MENDER_BROWSER_TEST=1`, `MENDER_REAL_RUNNER=1`, `MENDER_PUBLIC_TEST=1`), as are `rehearse.py`, `rehearse_ui.py` and `bench_models.py` (about $0.03 per demo loop).
- Docs: root README.md (whole-stack quick start), backend README.md (run guide), HANDOFF.md (code map, invariants, evidence, open items), AGENTS.md (agent rules).

## Current state
M1 to M3, the generic runner, per-workflow maps and stores, read healing, crash recovery and run pruning, cooldown_remaining_s, the Sentry products (Tracing, Logs, AI agent monitoring, Profiling, Session Replay), the redesigned dashboard and the inventory desk are merged into main (PRs #1 to #5). Open pull requests: #6 adds four read-only workflows on public and practice sites, and #7 (stacked on #6) adds creating a workflow from a sentence on those sites (services/backend/author.py and custom.py, loopback-only draft, keep and delete endpoints, quotas, a request guard and a pre-action veto) plus the dashboard panel. Everything was verified end to end with real Gemini, including through the dashboard in a real browser. Open: a Sentry dashboard (manual, UI only), a warm runner driver (Playwright startup is about 197 ms of the 367 ms fast path), and the limits listed in HANDOFF.md. Verify actual repo state yourself before trusting this paragraph. HANDOFF.md is the source of truth.
