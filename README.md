# Mender

Mender turns a web portal that has no API into a fast JSON endpoint that repairs itself when the site
changes.

A deterministic Playwright runner executes a workflow (steps and outputs from `contracts/workflows/`) with CSS
selectors from that workflow's map in `contracts/selectors/` (about 0.4 s, no model on the fast path). Two
workflows ship today: a permit lookup and a record editor that really changes a value. When the portal changes and a selector breaks, the backend
runs a Browser Use agent (Gemini) on the changed page, derives a CSS selector for the broken field from
the agent's recorded history, proves it by replaying the runner, and only then commits it. If the replay,
the output schema, or a canary check fails, the original selectors are restored. Sentry traces the whole
thing, including the agent.

```
                    POST /api/v1/run-workflow
 dashboard  ───────────────────────────────────────►  backend (FastAPI)
 (React)    ◄───────────────────────────────────────    │   ▲
                 JSON + heal records + cost             │   │ selector maps (locked, versioned)
                                                        ▼   │
                                  runner (Playwright) ──────┘        portal (the site to automate)
                                   fast path, no LLM  ─────────────►  (mock permit portal, Chaos Mode)
                                                        │ on failure
                                                        ▼
                                   Browser Use agent + Gemini ──► new selector ──► replay ──► commit or roll back
```

## Layout and owners

| Path | What | Owner |
| --- | --- | --- |
| `contracts/` | Shared schemas, types, fixtures, workflow definitions, per-workflow selector maps | all three, changes need agreement |
| `services/portal/` | Mock legacy permit portal with Chaos Mode (stdlib server) | Person 1 |
| `services/runner/` | Generic deterministic Playwright runner, setup scripts, demo reset | Person 1 |
| `services/backend/` | Recovery engine, API, Sentry, tools, tests | Person 2 |
| `services/dashboard/` | React dashboard that shows fast versus healed runs | Person 3 |

## Quick start

You need Python 3.12 with [`uv`](https://docs.astral.sh/uv/), Node 20+, and Google Chrome. From the
repository root:

```sh
# 1. Project venv with Playwright and its Chromium (used by the runner)
services/runner/setup_venv.sh

# 2. Backend settings: copy the example, then set GOOGLE_API_KEY, GEMINI_MODEL, optionally SENTRY_DSN
cp services/backend/.env.example services/backend/.env

# 3. The mock portal (terminal 1), and optionally the local record site for the write demo
.venv/bin/python services/portal/server.py
.venv/bin/python services/backend/sandbox/records_site.py --port 3100   # optional, terminal 1b

# 4. The backend (terminal 2)
MENDER_RUNNER_PYTHON="$PWD/.venv/bin/python" \
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements.txt \
  python -m uvicorn services.backend.main:app --env-file services/backend/.env \
  --host 127.0.0.1 --port 8000 --workers 1

# 5. The dashboard (terminal 3)
cd services/dashboard && npm ci
VITE_USE_MOCKS=false VITE_SENTRY_ORG=<your-sentry-org> npm run dev   # or put these, and VITE_SENTRY_DSN, in .env.local
```

Open the dashboard at http://127.0.0.1:5173 and the portal at http://127.0.0.1:3000/permits/apply.
Without a `SENTRY_DSN` everything still runs; Sentry is just off.

## Public sites

Two read-only workflows run against the real Wikipedia and python.org, with no setup beyond the venv: pick
**Wikipedia** (type an article title, read its heading) or **Python releases** (read the newest release) in the
dashboard. They show the fast path on sites we do not own. Their live checks are opt-in and free:
`MENDER_PUBLIC_TEST=1 ... -m unittest services.backend.tests.test_public_sites`. You cannot use Chaos Mode on a site you
do not own, and writes are never allowed on them.

## The demo

1. Pick a workflow (the picker lists what the backend can run), then **Trigger workflow** in the dashboard: the fast path, about 0.4 s, "Deterministic Playwright".
2. On the portal, click **Chaos Mode** (its submit button loses its id and moves into a modal).
3. **Trigger workflow** again: the runner fails, the dashboard switches to "Browser Use Agent Engaged",
   and about half a minute later returns the correct JSON with a committed heal record (old and new
   selector) and the agent's cost. Trigger once more: the fast path again, on the healed selector.
4. Open **View Sentry trace** for the request, the agent spans, and the selector change.
5. Before the next run click **Reset selectors** in the dashboard (restores the committed selectors; the
   healed one only matches Chaos Mode's page) and turn Chaos Mode off on the portal.

For the write demo, start the inventory site and open `http://127.0.0.1:3100/records` beside the dashboard:

1. The legacy desk has twelve named items, stock badges, a Low stock warning, filters, sortable columns and
   eight rows per page. Explore Orders, Suppliers and Reports, then return to Inventory. Choose
   `record-update`, set `record_id` to `SKU-1042` and `value` to `24.95`, then trigger the workflow.
   The seeded table changes from 19.95 to 24.95 and its "Last saved" time updates automatically, even though
   the runner uses a separate browser. A save reveals its row even under a filter or on another page, and
   adds an entry to Recent changes. You can also save directly in the site's price form. Supplier notes
   have a separate form and do not change prices.
2. Click **Break something** on the inventory page. Each click applies one more change, and a note beside the
   button says what changed: the save button moves into an authorization dialog, the Record ID box gets a new
   id, the saved value's test id is renamed, or decoy buttons and a search box appear. At most two changes
   that break a selector are active at once, so a repair never needs more than two agent runs. Click again and
   a sign-in wall replaces the form: the agent must stop and fail honestly, with no records and no writes.
   Trigger the workflow after each break to demonstrate the repair (one change, then two together), then once
   more for the fast path. **Restore site** removes every change.
3. The agent, replay and canary each save during a successful heal. Repeated sets are safe, and the
   `canary-record` row is visible too; "Last saved" may refer to it. Write workflows run only on local or
   allow-listed hosts.
4. Before repeating, reset `record-update` selectors in the dashboard and click **Restore site** on the page.
   To restore all twelve seed rows as well, `POST /reset` to the site on port 3100. That also clears chaos and
   writes, audit, supplier note, filters and last-save metadata. Reset the site between write demos;
   selector reset remains a separate backend operation.

Rehearse it unattended: `python -m services.backend.rehearse 5` (API) or
`services/backend/rehearse_ui.py` (through the dashboard in a real browser). Both spend about $0.03 per loop.

## How Sentry shaped Mender

The track asks for more than error monitoring, and we used it that way: five products, and each changed a decision.

- **Tracing** (browser, backend, runner and agent in one trace). Pressing Trigger starts the trace; the agent's
  four sequential model calls of about 5 s each showed up as the long bar, which made us compare eight Gemini
  models (90 paid trials). The default is now `gemini-3.5-flash-lite`: about 11 s and half a cent per heal,
  6x cheaper and 2.2x faster than the model we started with.
- **AI agent monitoring** (`gen_ai.*` spans, tokens, cost). It also caught a flaw in our own change: two models
  gave up early and the backend treated that as final, so `agent_blocked` became retryable.
- **Logs** next to the spans. One failed recovery had opened six issues from log lines; we turned that off and
  fingerprinted our own events, so a failure is one issue and the alert fires only for `tier:agent`.
- **Profiling** on every trace (fast 0.4 s runs and 15 s heals).
- **Session Replay** on the dashboard, linked to the backend issue through the shared trace.
- **Runner phase timings** in the trace showed the fast path is about 367 ms but only about 151 ms is runner work;
  Playwright import and driver start cost about 197 ms. Next: a warm driver.

Details and what Sentry did not do (two summary attributes never became queryable, no dashboard from the plugin)
are in [services/backend/HANDOFF.md](services/backend/HANDOFF.md#sentry).

## Tests

| Where | Command |
| --- | --- |
| Backend (default, no model calls) | `uv run --no-project --python 3.12 --with-requirements services/backend/requirements-test.txt python -B -m unittest discover -s services/backend/tests` |
| Runner (12 tests) | `cd services/runner && ../../.venv/bin/python -m unittest test_execute` |
| Dashboard (55 tests) | `cd services/dashboard && npm run typecheck && npm test` |

Opt-in tests that use a real browser, the real runner, or paid Gemini calls are listed with their flags
and costs in [services/backend/README.md](services/backend/README.md#tests-and-tools).

## Where to read next

- [services/backend/README.md](services/backend/README.md): run guide, settings, recovery rules, Sentry, tools.
- [services/backend/HANDOFF.md](services/backend/HANDOFF.md): code map, invariants, evidence, open items.
- [contracts/README.md](contracts/README.md): the shared response and selector contracts.
- [services/dashboard/README.md](services/dashboard/README.md), [services/runner/README.md](services/runner/README.md),
  [services/portal/README.md](services/portal/README.md): each service's own guide.
- [services/backend/proposals/](services/backend/proposals): changes proposed to other owners, not applied.
- [PRODUCT.md](PRODUCT.md): who the dashboard is for and how it should feel.

## Status

Backend milestones M1 to M3 are merged, along with the real runner, portal and dashboard. Branch
`codex/browser-use-recovery` adds the generic runner, per-workflow selector maps, canary-verified read healing,
crash recovery, the workflow picker, `cooldown_remaining_s`, and the Sentry products above. Reads work on any
reachable site; workflows that change data run only on local or allow-listed sites; login and captcha walls fail
instead of being bypassed. Open items and known limits are in the backend handoff.
