# Mender: context for Claude Code

## What this is
Mender is a hackathon project (LA Hacks, AI track, 24 hours, software only). It turns an API-less web portal into a fast JSON endpoint that repairs itself when the site changes.
- A deterministic Playwright runner drives a mock legacy portal using CSS selectors from contracts/selectors.json. No LLM on the fast path.
- When the portal changes (Chaos Mode) a selector breaks and the runner fails with a failure artifact.
- The backend catches that, spawns a Browser Use agent (Gemini) to complete the workflow on the changed page, derives a CSS selector for the broken field from the recorded history, verifies it by replaying the runner, patches selectors.json, and returns the result.
- Sentry (tracing, logs, AI agent monitoring) wraps everything. It is a judged prize track, so Sentry must be load-bearing, not decoration.

## Who owns what
- Person 1: /services/portal and /services/runner. Person 3: /services/dashboard. Person 2 (the user, who you work for): /services/backend. /contracts holds shared interfaces.
- You author code only under /services/backend. Never edit /contracts or others' folders. The one exception: runtime updates of selectors.json (including version bump) by the healer. Contract docs or fixture changes go in a separate commit as proposals for the contracts owner. The user once authorized cross-owner fixes (the runner CLI, selectors.json target_url, reset_demo.py, portal permit echo) with "fix everything first"; those are in their own commits for the owners to review. Do not repeat that without a fresh instruction.
- Branch: codex/browser-use-recovery. Push only to it. Never merge to main.

## Prize tracks the demo must support
Sentry (Best Use of Sentry), Browser Use, MLH Best Use of Gemini API. Cognition/Devin PR step is a stretch goal, not built. The demo: run a lookup (fast, about 300 ms, no LLM), click Chaos Mode on the mock portal, rerun, watch the dashboard switch to "Browser Use Agent Engaged", get correct JSON back, then show the Sentry trace, agent spans and the selector diff. It must be repeatable five times in a row. Prefer simple and deterministic over clever.

## Architecture decisions (settled, do not relitigate)
- Runner CLI is site-agnostic: python runner/execute.py --workflow <id> --params '<json>' --run-id <uuid> (optional --sentry-trace, --baggage). Success: exit 0, one JSON object. Failure: non-zero exit, runs/<run_id>/failure_payload.json and failure.png. Endpoint: POST /api/v1/run-workflow with {"workflow": "...", "params": {...}}. No permit-specific code in the backend.
- Each workflow has a definition: top-level goal, ordered steps, params_schema, output_schema, optional canary (volatile paths may be excluded). The ordered steps are authoritative for execution order. selectors.json field order means nothing.
- Selectors are CSS. Browser Use history gives attributes, XPath and node identity, not trusted CSS, so derive candidates and prove uniqueness on the live page. Runner replay is the real verification. Never accept a selector because the agent produced it.
- Browser Use 0.13.11 with Gemini (ChatGoogle), imported lazily and off the event loop. The fast path never imports it.
- Transactional recovery: baseline snapshot, one failed field patched per attempt, provisional patches kept only while replay shows forward progress (failure at a later ordered step), commit only after full replay, output schema validation and the canary pass. Otherwise restore the baseline as a NEW higher version, never reuse a version. Max 3 agent invocations, one monotonic 240 s deadline (stop work at 210 s, last 30 s reserved for cleanup). Replay and canary run under the already-held exclusive lock without reacquiring it.
- Recovery runs as a shielded background task per workflow that waiters join. A client disconnect must not cancel it. One Uvicorn worker. Agent errors, timeouts and no-result may retry the same field within the 3 cap. Ambiguous evidence and invalid candidates abort.
- Failure cooldown: one completed failure per workflow is kept in memory for 15 s after cleanup. The key is workflow, failed step, old selector, the full selector map (taken after cleanup, since rollback bumps the version) and a hash of the failure artifact. Cache hits never extend expiry. Never cache config errors, failures without valid runner evidence, cancellations, or failed cleanup or restoration.
- Response: heal_records, error, agent_cost_usd, agent_duration_ms are approved and enabled. Failures are HTTP 200 with status="failed", healed=false, data={}, structured error, no top-level diff. Cost and agent duration appear only on the request that started recovery, only when reliable, never 0 for unknown. error.message must be safe to show (no keys, paths, raw prompts, stack traces). heal_records describe the selector transaction; status describes the caller's own run.
- Scope: reads work on any reachable site; workflows that change data (`"mutates": true`) run only on loopback or `MENDER_WRITE_HOSTS` hosts, enforced in main.py. Login or captcha walls are never bypassed (agent_blocked). Write demos use sandbox/records_site.py.
- Reset for demo rehearsals: POST /api/v1/admin/reset (loopback only) restores the selectors from git HEAD as a new version and clears the cooldown. GET /api/v1/status shows why the backend is blocked.

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
5. Scope discipline: no Redis, database, retry endpoint, persistent cooldown, dashboard work, real portal integration, crash recovery or automatic PR generation unless the user says so.

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
- Person 1: per-step Playwright timeouts of about 2 s; chaos mutations that leave at least one unique CSS-addressable attribute per changed element (a heal cannot recover if every attribute and class is randomized); the failure payload contract. The cooldown also needs a failure artifact whose page URL, DOM snippet and error message are stable between runs (no tokens or timestamps), or it never hits.
- Person 3: dashboard must treat the new response fields as optional, show unknown cost as "n/a", show "retry in N s" during cooldown, wait at least 240 s for a response, and note that heal_records describe the selector transaction while status describes the caller's run.
- Contracts owner: approval of any new response or selector fields. Open questions on PR #1: agent_duration_ms as the sum of SDK step durations, and empty heal_records omitted rather than sent as [].

## Commands
Run from the repository root with Python 3.12 and uv.
- Default tests (mocked agent, no paid calls): `uv run --no-project --python 3.12 --with-requirements services/backend/requirements-test.txt python -B -m unittest discover -s services/backend/tests`
- Paid live and real-browser tests are opt-in (`MENDER_LIVE_TEST=1`, `MENDER_BROWSER_TEST=1`); see README.md.
- Run guide: README.md. Agent handoff and invariants: HANDOFF.md. Agent rules: AGENTS.md.

## Current state
M1, M2 and M3 are implemented on codex/browser-use-recovery (M3 commit ad8b0e5, PR #1 open against main). origin/phase-1 (Person 1's portal and runner) is merged; the runner now speaks the agreed CLI, contracts/selectors.json target_url is the real portal, reset_demo.py goes through the backend, and the portal echoes the permit id for a meaningful canary (cross-owner edits are in their own commits for review). Full-stack check: `python -m services.backend.rehearse 5` passed 5/5 with real Gemini. See HANDOFF.md, "Integration with Person 1's real runner". Sentry delivery was verified live against project mender-backend (org tanish-misra): single trace with agent, model and runner spans, token attributes on the invoke_agent span, one grouped issue, logs with trace IDs. The DSN is in the ignored services/backend/.env only. Default suite: 88 tests, OK, 11 opt-in skipped. Verify actual repo state yourself before trusting this paragraph. HANDOFF.md in /services/backend is the source of truth.
