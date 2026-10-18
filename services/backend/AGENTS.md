# Backend agent instructions

These instructions supplement the repository and global AGENTS.md instructions.

## Start here

1. Read the [root README](../../README.md), [the shared contracts](../../contracts/README.md),
   [the run guide](README.md), and [the handoff](HANDOFF.md). [CLAUDE.md](CLAUDE.md) holds the
   project brief, working agreement, and audit checklist.
2. Inspect the current branch and working tree before editing. Preserve unrelated changes.
3. Trace the relevant entry point, callees, and tests using the handoff's code map. Read
   actual source before relying on a prose description.

## Current scope and boundaries

- M1 (single field), M2 (transactional multi-field recovery) and M3 (failure cooldown,
  finalized `heal_records`, reset and status endpoints) are merged into `main` (PR #1). The
  generic runner, per-workflow maps, read healing, crash recovery, `cooldown_remaining_s`,
  the workflow picker and the Sentry products are on branch `codex/browser-use-recovery`
  (PR for the user to merge; never merge it yourself). New work needs an explicit instruction.
- Backend source, tests, fixtures, and docs belong under `services/backend/`. The portal,
  runner, dashboard, and `contracts/` belong to other owners. Changes there need an explicit
  instruction, go in their own commit, and are for the owner to review. Runtime selector
  updates and version bumps by the healer are always allowed. The user has authorized
  contract and cross-folder changes for the current branch; ask again for anything new.
- Treat the shared JSON schemas and models as authoritative. Import shared models instead of
  duplicating them. A contract change needs all three owners; write a proposal instead.
- Keep workflow behavior site-agnostic. Ordered steps, outputs, the `goal`, a required canary and
  the optional `mutates` flag belong to the definitions in `contracts/workflows/`, the only place
  they live. Each workflow has its own map in `contracts/selectors/<id>.json`; `fields` is a lookup.
- Keep `.env` and generated `state/` artifacts out of Git. Never print API keys or DSNs or
  include local secrets in examples, fixtures, logs, commits, or reviews.
- Use the global rigorous-coding, deliberate-thinking, ponytail, and adversarial-verification
  skills when their criteria apply. Use no em dashes.

## Changes must preserve

- No Browser Use imports or model calls on deterministic success. Its cold import runs off
  the event loop only after a runner failure.
- One run ID per subprocess, separate stdout/stderr, schema validation, and failure
  artifacts belonging to that run before starting the agent.
- Unique field grounding using executed action/result/element evidence and workflow order.
  Agent completion text cannot authorize a selector change.
- One locked baseline, accumulated atomic patches, runner replay, and rollback of the whole
  transaction on terminal failure. Every workflow requires a canary. One lock per workflow.
- Recovery owns its task and deadline. Request cancellation must not cancel it. Waiters
  shield the task and replay with their own params and fresh run IDs.
- At most three agent invocations, a 240-second recovery budget with 30 seconds reserved for
  cleanup, and a five-second ordinary lock acquisition limit.
- Agent errors, timeouts, no-result and `agent_blocked` (the agent gave up, for example at a login or
  access wall) may retry within the cap. Ambiguous evidence, invalid candidates, and
  same/earlier-step replay failures abort.
- Every selector write, including rollback and reset, advances the version. Rollback
  failure blocks further execution until reset and server restart.
- Responses follow the shared schema. `error`, `heal_records`, `agent_cost_usd` and
  `agent_duration_ms` are enabled. Failure is HTTP 200, `status=failed`, `healed=false`,
  `data={}`, no `diff`. Cost and duration go only to the request that ran the agent, only
  when reliable. `error.message` must stay safe to show. Empty `heal_records` is omitted.
- Cooldown: one failed recovery per workflow for 15 s, never extended by hits, keyed on the
  post-cleanup selector map and a fingerprint that ignores class attributes. Never cache
  config errors or failed cleanup. Records are never fabricated for agent errors or
  ambiguous evidence.
- Writes: a workflow with `mutates: true` runs only on loopback or `MENDER_WRITE_HOSTS`
  hosts, refused before the runner starts. Never bypass a login or captcha.
- Read healing: the agent reports the visible values, the backend finds the one element showing them,
  rejects selectors that embed a value, and requires the replay to read back the same values before the
  canary decides. Attribute-only read fields are refused up front.
- Crash recovery: the in-flight marker is written with the baseline and cleared only when the map is
  consistent; plain `baseline-*.json` backups are never auto-restored. `runs/` keeps the newest 50.
- Operator endpoints (`/api/v1/admin/reset`, `/api/v1/status`) stay loopback only.
- Sentry: only our fingerprinted events become issues (`LoggingIntegration(event_level=None)`;
  logs stay as Sentry Logs). Keep the `tier` tag (`deterministic` or `agent`), the stable
  fingerprints, the `gen_ai.*` agent span attributes, the `runner.<phase>_ms` span data, profiling,
  and the flat `recovery.*` attributes on the `healer.summary` span (reliable values only). The failed-recovery alert filters on `tier:agent`.
- Terminal output uses Rich without emojis. Keep cleanup in the renderer; preserve original
  log records, literal selectors, errors, and Sentry context.

## Verification and reporting

Run the default suite from the repository root. It makes no model calls and skips the
opt-in tests:

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-test.txt \
  python -B -m unittest discover -s services/backend/tests -v
uv run --no-project --python 3.12 --with ruff ruff check --isolated --select E4,E7,E9,F services/backend
```

Opt-in checks (flags and commands are in the run guide): real DOM and sandbox tests
(`MENDER_BROWSER_TEST=1`), real runner and portal (`MENDER_REAL_RUNNER=1`), and paid Gemini
runs (`MENDER_LIVE_TEST=1`, `rehearse.py`, `rehearse_ui.py`, `bench_models.py`). Paid calls stay
opt-in, and you report their cost.

Attack the behavior changed, including a case that would reject an incorrect repair (mutate
the code in an isolated process and confirm a named test fails). Report the exact commands
and outcomes, fixture versus real integration coverage, and unresolved gaps. Do not claim
the 400 ms fast-path target from fixture runs. Sentry delivery is verified by querying the
`mender-backend` project (traces, issues, logs), not by unit tests; recheck it after changing
instrumentation. Keep documentation consistent with source.
