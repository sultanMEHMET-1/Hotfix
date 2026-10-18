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

Instrument Sans for headings and the ratio (display), Space Grotesk for prose and labels (the Telogify body face; it has no italic, so nothing is italicised), IBM Plex Mono for every measured value, selector, id and timestamp, always with tabular figures. Scale: 14 / 15 / 17 / 22 / 34 / 52px, plus a fluid hero up to 8.5rem. Nothing that the audience needs is under 14px.

## Structure

One page, top to bottom: a sticky frosted header (the Portfolio's glass recipe: a faint tint, a blur, a hairline; the theme control is a bare icon that flips between a moon and a sun), "Selected:" and the site name with the workflow's goal, one control panel (workflow switcher, the Live switch and mock scenarios, the run action and its status), the measurement (fast replay and agent repair on one shared bar scale, durations in ms, s, then m s, the agent's cost only, and the ratio as the hero), the corrections ledger, and the run log. Corrections are git-style diffs with the evidence always visible in one plain sentence; there is nothing to expand. No tabs, no nested cards, no eyebrow labels. Square ink markers, never round dots.

## Motion

Sections blur-fade in once as they scroll into view (the Telogify and Portfolio recipe: spring, blur 10px to 0, rise 10px), and the first fold fades in on load. While the agent works, a live elapsed clock counts up. Tooltips are short (a few words), shown on hover after half a second and at once on keyboard focus. Everything collapses under `prefers-reduced-motion`.

## Accessibility

`<main>` landmark, skip link, one h1 and real h2 sections, 44px minimum targets, a single heavy-outline focus style, `role="status"` for the run state, `role="alert"` for errors, text never color-only (every state has a word).
