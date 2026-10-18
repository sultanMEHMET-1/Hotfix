# Direction contract - Mender Dashboard

seed: 0ca54b482aae85196c338edf375c345d (assigned index 3 of 7 grounded candidates, mode: operate)

## THESIS
A dashboard is not a cockpit. This surface refuses the instrument-panel/terminal costume every "self-healing" dev tool reaches for, and instead borrows the one working system built for exactly this job: a lab notebook recording an experiment under scrutiny, where a correction is never deleted - it's struck through, re-authorized, and left visible as proof of rigor. That convention *is* the commit/rollback story.

## OWN-WORLD
Vellum/graph-paper ground (`#F6F1E7`), faint iron-ink grid at 6% opacity. Iron-black ink (`#201D1A`) for body and rules. Bottle-green litmus ink (`#2F5D3A`) for pass/committed. Oxblood correction ink (`#7A2323`) for struck/reverted entries - replaces the prior amber-LED "healing" accent; the in-progress state is a wet-ink amber (`#9C5B1E`), closer to a fresh reagent stain than a warning light. No drop shadows, no rounded pill badges - ledger pages lie flat; structure comes from hairline rules and double-ruled column heads, the way a bound notebook rules its own margins. Type: IBM Plex Serif for labels/body (a workhorse serif, not a display face), IBM Plex Mono for every measured value and selector (the notebook's own numerals).

## STORY
A presenter (or an engineer reading it later) sees a run as a lab entry: timestamp, the measured result, and - when the agent intervened - a visible correction trail. Trust comes from seeing what was struck out, not just what's current.

## FIRST VIEWPORT
Header reads like a notebook's running-head: "Mender" as the experiment title, `permit-application` as the specimen id. Control row is the day's entry line: Trigger action, a litmus-strip status indicator, scenario selector as ruled tabs. Benchmark cards become two measurement blocks, ruled not boxed. Latency chart is a ruled strip chart. The Visual Diff Viewer is the notebook's correction log - each heal record a lab-notebook correction, old value struck in oxblood, new value recorded in green ink, "Why" as the researcher's margin note. Run log is a dated entry table, double-ruled header.

## FORM
Chemistry lab notebook / titration log (own grounded candidate, resonance rank 3 of 7; see `services/dashboard/design/NOTES.md` history for the full candidate list and the courtroom-evidence-board / airport-signage / emission-line-spectrogram challengers it was weighed against).

## FINISH
Unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
