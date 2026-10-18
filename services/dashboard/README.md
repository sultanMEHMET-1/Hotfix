# Mender Dashboard (`/services/dashboard`)

Owner: Person 3. A React + Vite + Tailwind single-page app that runs a workflow through the Mender backend and shows how it was served: the deterministic fast path, or a repair by the Browser Use agent (with the old and new selectors, the cost, and a Sentry trace link). It also lets you create a new read-only workflow from a sentence on four public sites. It consumes `WorkflowExecutionResponse` and `WorkflowSummary` from `contracts/api_types.ts` (imported read-only through the `@contracts` alias).

## Design

The look is a printed lab ledger: vellum paper (warm espresso in dark mode), hard ink rules, and a rule that an applied result is printed while one that was not applied is only drawn. Type is Instrument Sans for headings, Space Grotesk for text, IBM Plex Mono for every measured value and selector. The header is a sticky frosted bar with a single moon and sun icon that flips the theme (applied before first paint, so a refresh never flashes the other one). Sections blur-fade in once as they scroll into view, and tooltips are a few words. The built system is described in `design/DESIGN.md`; `design/DIRECTION.md` has the original notebook idea and `design/PAPER_PROMPT.md` the first brief. The Paper exports are the earlier direction, kept as history.

## Run

```bash
npm ci
npm run dev        # http://127.0.0.1:5173 (bound to localhost on purpose, see below)
npm run typecheck && npm test   # 85 tests, independent of any .env.local
npm run build
```

## Live and sample modes

The **Live** switch (outlined while off, filled while on) chooses where responses come from:

- **Off (sample data, no backend needed).** Responses are the contract fixtures in `contracts/fixtures/workflow_*.json`. **Fast**, **Heal** and **Rollback** buttons pick which canned outcome the next Trigger returns (Fast after about 300 ms, the others after 5 s). Useful for rehearsing the screens and for a demo without an API key. The speed card shows fixture figures, labelled as samples.
- **On (the real backend).** Start the portal and backend (see the root README), then `VITE_USE_MOCKS=false npm run dev`, or put the variables in the git-ignored `.env.local` (start from `.env.example`). The dev server proxies `/api` to `localhost:8000`, so no CORS setup is needed, and it binds to `127.0.0.1` because the backend trusts the proxy as a loopback caller for its admin and creation endpoints. Do not run it with `--host` or a tunnel while the backend is live.

What the UI does:

- **Workflow picker.** Asks `GET /api/v1/workflows` and offers each workflow by the name of its site (Permit portal, Inventory desk marked "writes", Wikipedia, Python releases, Books, Quotes; a created workflow is named by its goal). The title reads "Selected: <name>". **Trigger workflow** runs the selected one with its example parameters: `POST /api/v1/run-workflow {"workflow": <id>, "params": {...}}`. A finished run's result, status and error show only on the workflow it ran for.
- **Typed input** (live, public sites only). A read-only public workflow with a text parameter (Wikipedia's article title) shows a labelled box above **Trigger workflow**, filled with the example. Enter runs it, an empty box disables the trigger and says why, and the value is sent as the workflow's parameter. Values are kept per workflow until reload. Sample mode, the permit portal and the inventory desk keep their fixed examples.
- **Result.** A finished run prints what it read (for example `heading  Ada Lovelace`) under the controls, as a ledger line in the monospace face.
- **Reset selectors** (live only). Calls the backend's loopback-only `POST /api/v1/admin/reset` for the selected workflow, to put its original selectors back between demo runs. It is disabled while a run is in progress, shows the backend's own message if it refuses, and says so if the backend stays blocked.
- **Corrections pile up.** Every repair this session stays in the Corrections list, newest first, one group per run (a rolled-back attempt too), shown as diffs with one plain sentence on what the agent did. A run that changes nothing neither adds nor removes anything. **Clear corrections** hides them, and a successful **Reset selectors** clears the selected workflow's list, since the repairs were undone. The list is per workflow and lives in the page, so a reload empties it.
- **Create from a sentence** (Wikipedia, Python releases, Books, Quotes). A box with one-click example sentences that were each run for real. **Create workflow** takes under a minute and about a cent, with a live clock, then shows a preview (steps in plain words, the sample JSON result, cost and time) to **Save** or **Discard**. A saved workflow joins the picker and can be deleted. Saving and deleting wait while a run is in flight, and the panel starts fresh when the selection moves to another site. The backend's own refusal message is shown as it is; the always-visible limits list says what is refused.
- **Honest numbers.** Until a real run exists, the speed card shows "n/a". Durations read as ms, then s, then minutes. Only the agent has a cost (a fast run never calls a model); it shows "Unknown" when the backend did not report one, never $0.
- **Failures say what happened.** "Reverted after a failed recovery" only when a `rolled_back` record exists, "Recovery failed, no selector changed" otherwise, "Rollback failed, operator action needed" if the rollback itself failed. A request error (the backend is down or blocked) is shown as such. A repeat of a failure inside the 15 s cooldown shows a live "retry in N s" countdown from `cooldown_remaining_s`.
- **View Sentry trace.** Links to `https://<org>.sentry.io/explore/traces/trace/<trace_id>/` (set `VITE_SENTRY_ORG`).

## Sentry in the browser

Set `VITE_SENTRY_DSN` (a JavaScript project) and the dashboard starts `@sentry/react` with:

- **Tracing rooted at the click.** Pressing Trigger starts a `ui.action.click` span, and the request carries `sentry-trace` and `baggage` headers through the proxy into the backend, so one trace shows the browser, `workflow.execute`, the runner, and the agent's model calls. (The click span and the request appear as siblings under the pageload in the trace tree; they share one trace id.)
- **Session Replay.** `VITE_SENTRY_REPLAY_RATE` (0 to 1, default 0.1) is the share of ordinary sessions recorded; sessions with an error are always recorded. Use `1` while demoing and rehearsing. Text is not masked, because the dashboard shows only demo data and a masked replay is useless on stage. A replay is linked to the backend's issues through the shared trace.

Without a DSN, nothing is sent. Tests pin their own environment (`vite.config.ts`), so they never read `.env.local` or send events.

A browser rehearsal of the whole demo through this UI (reset, fast run, Chaos Mode, heal, fast run) lives in `services/backend/rehearse_ui.py`.
