# Design notes — Mender Dashboard

Things the static exports (JSX/PNG) don't show.

## Impeccable polish pass (2026-10-17)

Ran an Impeccable-guided craft review on the existing Paper file (refinement, not a visual-world replacement — see `PRODUCT.md`). Two real defects found and fixed directly in Paper; **the `exports/*.jsx` and `screens/*.png` below predate this pass and are stale** for these specifics until re-exported:

1. **Contrast failure**: `--color-heal` (#D97706) used as small/body text measured ~3.2:1 against white — fails WCAG AA (needs 4.5:1). `--color-ok` (#1C8A4C) at bold 13–16px also falls short of the "large text" exemption (~4.4:1 vs. the 4.5:1 floor for text under ~18.6px bold). Added `--color-heal-text` (#9A5B0A, 5.4:1) and `--color-ok-text` (#17703D, 6.1:1) tokens for small/body text; the brighter originals stay reserved for dots, borders, backgrounds, and the ≥24px hero numerals (execution time, cost), where 3:1 is sufficient and the brighter color is correct. Dark-mode text uses the dot/border-bright colors directly (they already pass ≥4.8:1 against the dark surfaces), not the light-mode `*-text` tokens, which go muddy on dark backgrounds.
2. **Flat cards**: the benchmark cards and heal-record diff rows had a border only, no shadow — reads as decoration-without-depth per craft-floor guidance. Added `shadow.card` (benchmark cards) and `shadow.diffRow` (heal-record rows) — soft, offset blur, not a zero-offset color halo.

Both fixes were applied file-wide across all 8 frames via Paper's `find_nodes`/`update_styles`, not redrawn by hand, so visual structure and copy are unchanged.

## Mood & direction
Mood: **vehicle dashboard** (instrument-panel black with amber LED accents) — chosen deliberately over the more obvious "terminal/phosphor" dev-tool choice because the product's whole point is a fast/normal state vs. a loud warning state kicking in, which is what an instrument cluster communicates at a glance. Light mode is primary; one dark variant (`Desktop Dark / Healed result`) is included.

## Animation / motion
- **Self-Healing status pill** (`Healing (in progress)` frame): the amber glow ring around the pill (`shadow.pulseHeal` token, `0 0 0 4px rgba(217,119,6,0.15)`) should pulse — animate the ring's opacity/spread on a ~1.6s ease-in-out loop while a run is healing. Static export shows only the ring at full opacity.
- **Trigger button loading state**: label reads "Triggering…" at 60% opacity. In code, pair this with a small inline spinner before the label (not drawn in Paper) and disable the button for the request duration.
- **Diff viewer "in progress"**: the amber box with "⟳ Agent re-indexing the page…" should have the ⟳ glyph rotate continuously (spin animation) while `recovery_attempted` is true and no `heal_records` have arrived yet.
- **State transitions**: Idle → Fast Path / Healing → Healed or Rolled back should crossfade (150–200ms) rather than hard-cut, especially the status pill color and the benchmark card numbers, since the numbers are the hero and a hard cut reads as a layout jump.
- **Latency chart bars**: when a new run completes, the new bar should animate in from height 0 (200ms ease-out) and the chart should auto-scroll so the newest bar is visible on the right.

## Mobile breakpoint (390px)
- Single column throughout; benchmark cards stack vertically instead of 2-up.
- Visual diff panels stack **old-over-new** (not side-by-side) within each heal-record row — this is the one structural difference from desktop, called out explicitly in the brief.
- The mock scenario picker and "Open Sentry trace" button are left-aligned/full-width-adjacent rather than pinned to the right of a control row, since there's no horizontal room to keep them inline with the trigger button.
- Run log collapses to a single compact card per run instead of a table with columns (no room for a 5-column header at this width).
- Status bar is the standard Apple-style bar (white icons on the dark `--color-ink` header strip) per the mobile-status-bar guide; swap to `color: black` only if a future frame uses a light header background.

## States not fully explored
- The `rejected` heal-record outcome only appears in the Components frame (as a placeholder "confirm_checkbox" example) — no full-page frame uses it, since none of the three fixtures exercise it. Its treatment (neutral gray badge, muted/struck-through "healed" panel, same as rolled-back but gray instead of red) is a best guess and should be confirmed against real rejection copy when that path is implemented.
- Hover/focus states are only shown for the Trigger button in the Components frame. Other interactive elements (mock scenario picker tabs, Sentry button, run-log rows) will need hover states defined in code following the same pattern (darken background ~8%, no color hue shift).

## Tokens
- `tokens.json` includes a `colorDark` block for the dark-mode palette used in `Desktop Dark / Healed result`. Dark-mode diff panel backgrounds use semi-transparent `rgba()` fills rather solid tints (so they sit correctly on the dark elevated surface) — see `diffOldBg` / `diffNewBg` under `colorDark`.
- `shadow.pulseHeal` is the glow-ring box-shadow for the healing status pill; `shadow.activeTab` is the subtle shadow on the active segment of the mock-scenario picker.
