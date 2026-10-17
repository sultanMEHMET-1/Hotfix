# Backend agent instructions

These instructions supplement the repository and global AGENTS.md instructions.

## Start here

1. Read [the shared contracts](../../contracts/README.md),
   [the run guide](README.md), and [the review handoff](HANDOFF.md).
2. Inspect the current branch and working tree before editing. This work lives
   on `codex/browser-use-recovery`; preserve unrelated user changes.
3. Trace the relevant entry point, callees, and tests using the handoff's code
   map. Read actual source before relying on a prose description.

## Current scope and boundaries

- M1 is implemented and waiting for review. Stop after M1 review; M2 and M3
  require the user's explicit instruction to continue.
- Backend source, tests, fixtures, and docs belong under `services/backend/`.
  Portal, runner, and dashboard implementation belong to other team members.
- Treat the shared JSON schemas and models as authoritative. Import shared
  models instead of duplicating them. Contract source changes need explicit
  authorization; runtime selector updates and version bumps are already allowed.
- Keep workflow behavior site-agnostic. Ordered steps and the top-level `goal`
  belong to backend-owned workflow definitions. Selector `fields` is a lookup.
- Keep `.env` and generated `state/` artifacts out of Git. Never print API keys
  or include local secrets in examples, fixtures, logs, commits, or reviews.
- Use the global rigorous-coding, deliberate-thinking, ponytail, and
  adversarial-verification skills when their criteria apply. Use no em dashes.

## Changes must preserve

- No Browser Use imports or model calls on deterministic success. Its cold
  import runs off the event loop only after a runner failure.
- One run ID per subprocess, separate stdout/stderr, schema validation, and
  failure artifacts belonging to that run before starting the agent.
- Unique field grounding using executed action/result/element evidence and
  workflow order. Agent completion text cannot authorize a selector change.
- Locked backup, atomic patch, real runner replay, optional canary, and rollback
  on verification failure or delivered task cancellation.
- Every selector write, including rollback and reset, advances the version.
  Rollback failure blocks further execution until reset and server restart.
- Responses follow the shared schema. Unset/default optional fields can be
  omitted. M1 does not populate `heal_records` or implement shared flights.

## Verification and reporting

Run the default suite from the repository root:

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-test.txt \
  python -B -m unittest discover -s services/backend/tests -v
```

The default suite mocks model calls. Leave `MENDER_LIVE_TEST` unset for ordinary
checks. The opt-in live command and its local-browser prerequisites are in the
run guide; it uses the real configured Gemini account.

Attack the behavior changed, including a case that would reject an incorrect
repair. Report the exact commands and outcomes, fixture versus real integration
coverage, and unresolved gaps. Do not claim the 400 ms target or live Sentry
delivery from the existing tests. Keep documentation consistent with source.
