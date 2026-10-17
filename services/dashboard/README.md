# Mender Dashboard (`/services/dashboard`)

Owner: Person 3. A React + Vite + Tailwind single-page app that consumes `WorkflowExecutionResponse` from `contracts/api_types.ts` (imported read-only through the `@contracts` alias).

## Design workflow
Paper is the design source of truth. See `design/PAPER_PROMPT.md`: the design is created in Paper (local session with the Paper MCP), exported to `design/`, and the components are built from those exports.

## Run
```bash
npm install
npm run dev        # http://localhost:5173
npm run typecheck && npm test
```

## Mocks and the hour-15 handshake
- `VITE_USE_MOCKS=true` (default): responses are the contract fixtures in `contracts/fixtures/workflow_*.json`. The **Fast** scenario returns after ~300ms; **Heal** and **Rollback** return after 5s.
- Handshake: copy `.env.example` to `.env.local`, set `VITE_USE_MOCKS=false`, and start Person 2's FastAPI on `:8000`. The Vite dev server proxies `/api` to it, so no CORS setup is needed.
- `VITE_SENTRY_ORG` enables the "Open Sentry trace" deep-link.
