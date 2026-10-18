# Mender Dashboard (`/services/dashboard`)

Owner: Person 3. A React + Vite + Tailwind single-page app that consumes `WorkflowExecutionResponse` from `contracts/api_types.ts` (imported read-only through the `@contracts` alias).

## Design workflow
Paper is the design source of truth. See `design/PAPER_PROMPT.md`: the design is created in Paper (local session with the Paper MCP), exported to `design/`, and the components are built from those exports.

## Run
```bash
npm install
npm run dev        # http://localhost:5173
npm run typecheck && npm test   # 45 tests
```

## Live mode against the real backend

Start the portal and backend (see the root README), then:

```bash
VITE_USE_MOCKS=false VITE_SENTRY_ORG=<your-sentry-org> npm run dev
```

The dev server proxies `/api` to `localhost:8000`. The request is
`POST /api/v1/run-workflow {"workflow": "permit-application", "params": {"permit_id": ..., "applicant_name": ...}}`.
In live mode a **Reset selectors** button appears; it calls the backend's loopback-only
`POST /api/v1/admin/reset` to put the original selectors back between demo runs (it is disabled
while a run is in progress and shows the backend's own message if it refuses).

Failed runs are labeled by what actually happened: "Reverted after a failed recovery" only when a
`rolled_back` record exists, "Recovery failed, no selector changed" otherwise, and "Rollback failed,
operator action needed" if the rollback itself failed. "View Sentry trace" links to
`https://<org>.sentry.io/explore/traces/trace/<trace_id>/`.

A browser rehearsal of the whole demo through this UI lives in `services/backend/rehearse_ui.py`.

## Mocks and the hour-15 handshake
- `VITE_USE_MOCKS=true` (default): responses are the contract fixtures in `contracts/fixtures/workflow_*.json`. The **Fast** scenario returns after ~300ms; **Heal** and **Rollback** return after 5s.
- Handshake: copy `.env.example` to `.env.local`, set `VITE_USE_MOCKS=false`, and start Person 2's FastAPI on `:8000`. The Vite dev server proxies `/api` to it, so no CORS setup is needed.
- `VITE_SENTRY_ORG` enables the "Open Sentry trace" deep-link.
