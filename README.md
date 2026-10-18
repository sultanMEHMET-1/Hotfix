# Mender

Mender turns a web portal that has no API into a fast JSON endpoint that repairs itself when the site
changes.

A deterministic Playwright runner drives the portal with CSS selectors from `contracts/selectors.json`
(about 0.4 s, no model on the fast path). When the portal changes and a selector breaks, the backend
runs a Browser Use agent (Gemini) on the changed page, derives a CSS selector for the broken field from
the agent's recorded history, proves it by replaying the runner, and only then commits it. If the replay,
the output schema, or a canary check fails, the original selectors are restored. Sentry traces the whole
thing, including the agent.

```
                    POST /api/v1/run-workflow
 dashboard  ───────────────────────────────────────►  backend (FastAPI)
 (React)    ◄───────────────────────────────────────    │   ▲
                 JSON + heal records + cost             │   │ selectors.json (locked, versioned)
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
| `contracts/` | Shared schemas, types, fixtures, `selectors.json` | all three, changes need agreement |
| `services/portal/` | Mock legacy permit portal with Chaos Mode (stdlib server) | Person 1 |
| `services/runner/` | Deterministic Playwright runner, setup scripts, demo reset | Person 1 |
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

# 3. The mock portal (terminal 1)
.venv/bin/python services/portal/server.py

# 4. The backend (terminal 2)
MENDER_RUNNER_PYTHON="$PWD/.venv/bin/python" \
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements.txt \
  python -m uvicorn services.backend.main:app --env-file services/backend/.env \
  --host 127.0.0.1 --port 8000 --workers 1

# 5. The dashboard (terminal 3)
cd services/dashboard && npm ci
VITE_USE_MOCKS=false VITE_SENTRY_ORG=<your-sentry-org> npm run dev
```

Open the dashboard at http://localhost:5173 and the portal at http://127.0.0.1:3000/permits/apply.
Without a `SENTRY_DSN` everything still runs; Sentry is just off.

## The demo

1. **Trigger workflow** in the dashboard: the fast path, about 0.4 s, "Deterministic Playwright".
2. On the portal, click **Chaos Mode** (its submit button loses its id and moves into a modal).
3. **Trigger workflow** again: the runner fails, the dashboard switches to "Browser Use Agent Engaged",
   and about half a minute later returns the correct JSON with a committed heal record (old and new
   selector) and the agent's cost. Trigger once more: the fast path again, on the healed selector.
4. Open **View Sentry trace** for the request, the agent spans, and the selector change.
5. Before the next run click **Reset selectors** in the dashboard (restores the committed selectors; the
   healed one only matches Chaos Mode's page) and turn Chaos Mode off on the portal.

Rehearse it unattended: `python -m services.backend.rehearse 5` (API) or
`services/backend/rehearse_ui.py` (through the dashboard in a real browser). Both spend about $0.03 per loop.

## Tests

| Where | Command |
| --- | --- |
| Backend (default, no model calls) | `uv run --no-project --python 3.12 --with-requirements services/backend/requirements-test.txt python -B -m unittest discover -s services/backend/tests` |
| Runner | `cd services/runner && ../../.venv/bin/python -m unittest test_execute` |
| Dashboard | `cd services/dashboard && npm run typecheck && npm test` |

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

Backend milestones M1 to M3 (single-field repair, transactional multi-field repair, failure cooldown with
finalized heal records) are merged, along with the real runner and portal, and the dashboard. Reads work on
any reachable site; workflows that change data run only on local or allow-listed sites. Open items and known
limits are in the backend handoff.
