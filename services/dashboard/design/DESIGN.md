# DESIGN.md - Mender Dashboard

<!-- impeccable:design-schema 1 -->

## World

A printed lab ledger. It combines two things on purpose: the lab-notebook idea from `design/DIRECTION.md` (a correction is never deleted, it is struck through and left visible as proof) and the printed-card voice of the Telogify frontend (cream paper, hard ink rules, oversized type doing the work, a flat offset shadow that means "printed"). The one rule that joins them: **an applied result is printed, a result that was not applied is only drawn.** A committed selector change gets solid rules, a flat offset and a green stamp. A rolled back or rejected one gets dashed or dotted rules, no offset, and its proposed selector struck through, so it can never be mistaken for the live selector.

This replaces the earlier generic card-and-pill look. The Paper exports under `design/exports` and `design/screens` show that earlier direction and are kept only as history.

## Palette

Defined as RGB triplets in `src/styles/index.css`, light and a warm espresso dark. Color carries meaning only, and the accent is ink itself.

| Token | Light | Dark | Role |
|---|---|---|---|
| `ground` | `243 237 222` | `28 23 20` | page |
| `surface` | `251 247 236` | `38 31 27` | printed card |
| `ink` | `32 29 26` | `240 232 218` | text, rules, primary action |
| `ink-muted` / `ink-faint` | `84 76 66` / `105 96 82` | `196 184 166` / `165 153 135` | secondary text, never below 4.5:1 |
| `success` | `47 93 58` | `143 196 130` | fast path, committed |
| `warning` | `150 86 24` | `222 164 90` | the agent at work |
| `danger` | `122 35 35` | `230 138 126` | failed, struck, rolled back |

## Type

Instrument Sans for headings and the ratio (display), IBM Plex Serif for prose and labels, IBM Plex Mono for every measured value, selector, id and timestamp, always with tabular figures. Scale: 14 / 15 / 17 / 22 / 34 / 52px, plus a fluid hero up to 8.5rem. Nothing that the audience needs is under 14px.

## Structure

One page, top to bottom: running head (double rule), the workflow name and its goal, ruled workflow tabs, the run action and its status, demo controls (a dashed, subordinate group), the measurement (cached run, agent repair, and the ratio as the hero, with both bars on one shared scale), the corrections log, and the run log. No tabs, no nested cards, no eyebrow labels. Square ink markers, never round dots.

## Motion

One authored moment: when a result arrives, each committed correction is stamped onto the page (260ms, ease-out). While the agent works, a live elapsed clock counts up. Everything collapses under `prefers-reduced-motion`.

## Accessibility

`<main>` landmark, skip link, one h1 and real h2 sections, 44px minimum targets, a single heavy-outline focus style, `role="status"` for the run state, `role="alert"` for errors, text never color-only (every state has a word).
