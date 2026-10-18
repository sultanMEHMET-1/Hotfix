# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React 18 + Vite + TypeScript + Tailwind (existing codebase: `services/dashboard/package.json`).

## Users

Primary: a presenter driving a live demo (pitch, investor meeting, conference talk) with an audience watching a shared/projected screen. Secondary (inferred, not confirmed): an engineer checking the dashboard during day-to-day development of the self-healing workflow. *Inferred from the brief's emphasis on "must read well projected on a demo screen: big numbers, nothing tiny that matters" — not separately confirmed with the user.*

## Product Purpose

Mender runs a browser workflow (a permit-application form) against cached CSS selectors. When a selector breaks, an AI agent (Browser Use) visually re-indexes the page, heals the selector, and finishes the run. The dashboard is the front-of-house for this demo: in one glance it must show "cheap and fast when cached" versus "slow and expensive, but self-healing, when the page changed."

## Positioning

The mechanism a competing "flaky test" or "self-healing selector" product would not share: deterministic Playwright execution stays the default fast path (cached selectors, near-zero cost), and the agent is only invoked on failure, with every agent-made change going through a transactional heal — committed, rolled back, or rejected — never silently applied. The UI's job is to make that commit/rollback distinction visible and trustworthy, not just "AI fixed it."

## Operating Context

- Workflow under test: `permit-application` (a target browser form with semantic fields like `input_permit_id`, `submit_button`).
- Backend contract is fixed and external: `contracts/api_types.ts` / `contracts/fixtures/*.json`. The dashboard must consume `WorkflowExecutionResponse` as given and must not invent fields.
- A "Mocks ON/OFF" dev control and a Fast/Heal/Rollback mock scenario picker exist so the dashboard can be demoed without a live backend run.
- Observability: a Sentry trace id (`trace_id`) is surfaced per run; "Sentry not configured" is a valid, expected state.

## Capabilities and Constraints

- Must render three top-level run outcomes: `success` (fast path, cached selector), `healed` (agent repaired one or more selectors and committed), `failed` (recovery attempted but rolled back to the last good version).
- Per-field heal evidence (`HealRecord`) must show old vs. new selector, verification outcome (`committed` | `rolled_back` | `rejected`), version before/after, and the agent's reasoning/evidence trail.
- Cost (`agent_cost_usd`) can be legitimately absent/unknown and must never be rendered as `$0.00` when unreported.
- Must work at desktop (1280px demo/projector width) and mobile (390px) breakpoints, plus one dark variant.
- Do not touch `/contracts`, `/services/backend`, `/services/runner`, or `/services/portal` — this surface is UI-only.

## Brand Commitments

Product name "Mender." No existing logo, brand guideline doc, or locked palette beyond what the prior design pass chose (vehicle-dashboard mood, amber for the "healing" state) — treated as the current committed direction per the user's instruction to work from the existing Paper file, not restart it.

## Evidence on Hand

- `services/dashboard/design/PAPER_PROMPT.md` — the original design brief (frames, regions, realistic placeholder values, export requirements).
- `contracts/fixtures/workflow_success.json`, `workflow_healed.json`, `workflow_rolled_back.json` — real example API responses.
- An existing Paper file, "Mender Dashboard," with 8 built frames (Desktop Idle / Fast Path / Healing / Healed / Rolled back, Mobile Healed, Desktop Dark Healed, Components) and a prior export already committed to `services/dashboard/design/{exports,screens}/`, `tokens.json`, `NOTES.md`.
- No real user research, customer logos, testimonials, or pricing exist for this surface — none should be fabricated.

## Product Principles

1. Color carries meaning only (green = fast/healthy, amber = healing-in-progress, red = broken/rolled-back) — never decorative.
2. The commit/rollback distinction in the Visual Diff Viewer is the trust-building centerpiece of the product and must never look ambiguous (a rolled-back "healed" selector must look visibly *not applied*).
3. Big numbers are the hero (execution time, cost) because the whole pitch is "cheap+fast vs. expensive+self-healing" — nothing load-bearing should be small text on a projector.
4. Never fabricate or soften an "unknown" cost/value; an unreported number is a distinct state, not a zero.
5. The dashboard is a UI-only surface: product truth and API shape are owned by `/contracts` and must not be reinvented here.

## Accessibility & Inclusion

No standard explicitly required by the user. Carry over the prior pass's baseline (text contrast on color-coded states, no color-only signaling without an accompanying label/icon) as a working default; not a confirmed requirement.
