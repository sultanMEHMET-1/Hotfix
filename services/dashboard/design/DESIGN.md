# DESIGN.md — Mender Dashboard

<!-- impeccable:design-schema 1 -->

## World

Chemistry lab notebook / titration log. Full contract: `design/DIRECTION.md`. Replaces the prior "vehicle dashboard" instrument-panel direction (flagged by Impeccable's process as a working-tool costume — the category rut for an Operate surface — rather than a real identity).

## Palette

| Token | Value | Role |
|---|---|---|
| `vellum` | `#F6F1E7` | page ground |
| `vellum-raised` | `#FBF8F1` | card/entry surface |
| `rule` / `rule-strong` | `#D9CFBA` / `#B9AC8C` | hairline rules, no shadows |
| `ink` | `#201D1A` | body, structure |
| `ink-muted` | `#6B6459` | secondary |
| `green` / `green-bg` | `#2F5D3A` / `#E4EBE1` | pass / committed (litmus) |
| `amber` / `amber-bg` | `#9C5B1E` / `#F3E6D3` | in-progress (wet ink, not a warning light) |
| `oxblood` / `oxblood-bg` | `#7A2323` / `#F3DEDE` | struck / reverted |

All pairs verified ≥4.7:1 against the vellum ground (ink 14.9:1, green 6.8:1, oxblood 8.9:1, amber 4.7:1).

## Type

IBM Plex Serif (labels, body, copy) + IBM Plex Mono (every measured value, selector, trace id, timestamp) — both workhorse faces, not costume display type. Scale: 12/13/15/19/26/38px.

## Signature material

A 24px graph-paper grid at 6% ink opacity on every surface (`bg-grid` Tailwind utility), and a left-margin rule line (oxblood at 25% opacity) running the page's full height — the notebook's own ruled margin, not decoration.

## Signature convention

A rolled-back heal record is never just "red" — it follows the lab notebook's actual correction convention: the old selector is struck through in oxblood (the entry stays legible, never deleted), the new value is shown crossed in muted ink labeled "proposed" rather than applied, and the outcome reads "struck — reverted" rather than a generic failure badge. This is the one borrowed discipline that does the most work: it makes the commit/rollback distinction self-explanatory without a legend.

## Components

`StatusPill` is a litmus-strip indicator (colored tab + ruled label), not a pill/badge. `ControlRow`'s scenario picker is ruled tabs, not segmented pills. Cards in `BenchmarkCards` and `HealRecordRow` use hairline borders only — no drop shadows anywhere in this world. `RunLog` is a double-ruled entry table (`border-b-2 border-ink` head rule), not a bordered box.

## Known gaps / next pass

- No formal multi-agent finish review ran (no subagent capability exercised in this session for it); this was a single-pass self-review against craft-floor contrast/structure checks plus a real headless-Chrome render of the idle state and a full RTL integration test (`App.test.tsx`) covering fast/heal/rollback states.
- Mobile (390px) and a dark variant were not rebuilt in this world; both existed for the prior Paper direction and should be redone against this one before the demo ships on those surfaces.
- The Paper file ("Mender Dashboard") still reflects the old vehicle-dashboard world and was intentionally left untouched — this pass happened code-led, directly in `services/dashboard/src/`, per Impeccable's rule that an Operate surface builds code-led regardless of recorded default.
