# Mender Dashboard (`/services/dashboard`)

Owner: Person 3. A React + Vite + Tailwind single-page app that runs a workflow through the Mender backend and shows how it was served: the deterministic fast path, or a repair by the Browser Use agent (with the old and new selectors, the version history, the cost, and a Sentry trace link). It consumes `WorkflowExecutionResponse` and `WorkflowSummary` from `contracts/api_types.ts` (imported read-only through the `@contracts` alias).

## Design
The look is a printed lab ledger: vellum paper, hard ink rules, and a rule that an applied result is printed while one that was not applied is only drawn. The built system is described in `design/DESIGN.md`; `design/DIRECTION.md` has the original notebook idea and `design/PAPER_PROMPT.md` the first brief. The Paper exports are the earlier direction, kept as history.

## Run
```bash
npm ci
npm run dev        # http://127.0.0.1:5173 (bound to localhost on purpose, see below)
npm run typecheck && npm test   # 58 tests, independent of any .env.local
npm run build
```

## Live mode against the real backend

Start the portal and backend (see the root README), then:

```bash
VITE_USE_MOCKS=false npm run dev
```

Or put the variables in the git-ignored `.env.local` (start from `.env.example`). The dev server proxies `/api` to `localhost:8000`, so no CORS setup is needed, and it binds to `127.0.0.1` because the backend trusts the proxy as a loopback caller for its admin endpoints. Do not run it with `--host` or a tunnel while the backend is live.

What the UI does in live mode:

- **Workflow picker.** The dashboard asks `GET /api/v1/workflows` and offers each workflow (the permit lookup, and the record editor, badged "writes" because it changes data). **Trigger workflow** runs the selected one with its example parameters: `POST /api/v1/run-workflow {"workflow": <id>, "params": {...}}`.
- **Reset selectors.** Calls the backend's loopback-only `POST /api/v1/admin/reset` for the selected workflow, to put its original selectors back between demo runs. It is disabled while a run is in progress, shows the backend's own message if it refuses, and says so if the backend stays blocked.
- **Honest numbers.** Until a real run exists, the speed and cost cards show "n/a" (mock mode shows fixture placeholders instead). Cost is "Unknown" when the backend did not report one.
- **Failures say what happened.** "Reverted after a failed recovery" only when a `rolled_back` record exists, "Recovery failed, no selector changed" otherwise, "Rollback failed, operator action needed" if the rollback itself failed. A request error (the backend is down or blocked) is shown instead of "Idle". A repeat of a failure inside the 15 s cooldown shows a live "retry in N s" countdown from `cooldown_remaining_s`.
- **View Sentry trace.** Links to `https://<org>.sentry.io/explore/traces/trace/<trace_id>/`.

## Sentry in the browser

Set `VITE_SENTRY_DSN` (a JavaScript project) and the dashboard starts `@sentry/react` with:

- **Tracing rooted at the click.** Pressing Trigger starts a `ui.action.click` span, and the request carries `sentry-trace` and `baggage` headers through the proxy into the backend, so one trace shows the browser, `workflow.execute`, the runner, and the agent's model calls. (The click span and the request appear as siblings under the pageload in the trace tree; they share one trace id.)
- **Session Replay.** `VITE_SENTRY_REPLAY_RATE` (0 to 1, default 0.1) is the share of ordinary sessions recorded; sessions with an error are always recorded. Use `1` while demoing and rehearsing. Text is not masked, because the dashboard shows only demo data and a masked replay is useless on stage. A replay is linked to the backend's issues through the shared trace.

Without a DSN, nothing is sent. Tests pin their own environment (`vite.config.ts`), so they never read `.env.local` or send events.

## Mocks and the hour-15 handshake
- `VITE_USE_MOCKS=true` (default): responses are the contract fixtures in `contracts/fixtures/workflow_*.json`, and the workflow picker offers two canned workflows. The **Fast** scenario returns after ~300ms; **Heal** and **Rollback** return after 5s.
- Handshake: copy `.env.example` to `.env.local`, set `VITE_USE_MOCKS=false`, and start the backend on `:8000`.
- `VITE_SENTRY_ORG` enables the "View Sentry trace" deep-link.

A browser rehearsal of the whole demo through this UI (reset, fast run, Chaos Mode, heal, fast run) lives in `services/backend/rehearse_ui.py`.
