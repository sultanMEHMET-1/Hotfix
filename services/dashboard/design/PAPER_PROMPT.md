# Paper design prompt — Mender Dashboard

Paper is the design source of truth for `/services/dashboard`. The code is built from what Paper produces here, so we design in Paper first and never redraw code in Paper afterwards.

## How to run this (on your laptop)

1. Open the Paper desktop app, create a file called **Mender Dashboard**, and turn on Paper's MCP server.
2. In your local clone, check out the `claude/fervent-feynman-6z9ipu` branch and start Claude Code in the repo root. Run `/mcp` to confirm the Paper tools are listed.
3. Paste everything under **Prompt for the local agent** below.
4. Review the canvas in Paper and iterate with the agent until you're happy. Your edits in Paper are welcome; the export step reads whatever is on the canvas.
5. Make sure the agent finishes the **Export** step, then commit and push `services/dashboard/design/**`.

---

## Prompt for the local agent

You are designing the Mender developer dashboard **in Paper, using the Paper MCP tools**. Work only on the Paper canvas and in `services/dashboard/design/`. Do not write application code, and do not edit anything outside `services/dashboard/design/`. Never touch `/contracts`, `/services/backend`, `/services/runner` or `/services/portal`.

### What the product is
Mender runs a browser workflow (a permit-application form) with cached CSS selectors. When a selector breaks, an AI agent visually re-indexes the page, heals the selector and finishes the run. The dashboard is the demo's front-of-house. In one glance it must show *cheap and fast when cached* versus *slow and expensive, but self-healing, when the page changed*.

### Data the UI shows (from `contracts/api_types.ts`, do not invent other fields)
```ts
interface WorkflowExecutionResponse {
  status: "success" | "healed" | "failed";
  execution_time_ms: number;
  data: Record<string, unknown>;
  healed: boolean;
  trace_id: string;
  diff?: { old_selector: string; new_selector: string };
}
```
Use these realistic values in every frame:
- workflow: `permit-application`
- fast run: `310ms`, cost `$0.0000`
- healed run: `12,400ms`, cost `$0.0381`
- selector diff: old `#submit-btn` → new `button[data-action="submit"]`
- trace id: `4f9c2a7e1b3d4c8e9a0f6b2d7c1e5a39`

### Frames to create (one canvas)
| Frame | Width | State |
| --- | --- | --- |
| `Desktop / Idle` | 1280 | Nothing run yet; benchmark cards show baseline numbers greyed; diff card empty state |
| `Desktop / Fast Path result` | 1280 | Green pill "Fast Path · Cached Selector"; 310ms / $0.0000 highlighted; diff card says "No selector changes" |
| `Desktop / Healing (in progress)` | 1280 | Pulsing amber pill "Self-Healing Loop · Agent Re-indexing"; Trigger button in loading state; spinner/progress in the diff card |
| `Desktop / Healed result` | 1280 | Healed pill; 12,400ms / $0.0381 highlighted against the fast baseline; diff populated; Sentry button active |
| `Mobile 390 / Healed result` | 390 | Same as above, single column, diff stacked old-over-new |
| `Components` | free | Every reusable piece with its states, side by side (see below) |

### Required regions, top to bottom
1. **Header**: "Mender" wordmark, workflow id chip `permit-application`, and a **Mocks ON/OFF** toggle on the right (a dev control, so keep it visually quiet).
2. **Control row**: primary **Trigger Workflow** button (calls `POST /api/v1/run-workflow`), the **status pill**, and a **Simulate Heal** switch (only meaningful when mocks are on).
3. **Benchmark cards**, 2-up:
   - *Execution time*: "Deterministic Run 310ms" vs "Agent Exploration 12,400ms", with a visual ratio (~40× slower).
   - *Cost*: "Cached Run $0.0000" vs "Agent Run $0.0381".
   Numbers are the hero; use a monospace face for them.
4. **Latency chart**: bar chart of the last ~10 runs (mix of ~300ms fast bars and ~12,000ms healed bars), colored by run type.
5. **Visual Diff Viewer** card: side-by-side panels. The left is red, labelled "Old selector", showing `#submit-btn` struck through or tinted red. The right is green, labelled "Healed selector", showing `button[data-action="submit"]`. Include an **Open Sentry trace ↗** button showing the trace id.
6. **Run log**: compact table with time, status, duration, cost and trace id.

### Components frame must include
- Status pill in four states: idle (neutral), fast path (green), self-healing (amber, show the pulse as a glow ring), healed (green with an amber "healed" badge), plus failed (red).
- Trigger button: default, hover, loading, disabled.
- Benchmark card, diff card (empty / populated), Sentry button (enabled / disabled with a "Sentry not configured" hint), run-log row (success / healed / failed), Mocks toggle, Simulate Heal switch.

### Design intent (a starting point; make the real visual decisions yourself)
- Developer-tool aesthetic: calm neutral surfaces, high contrast, color used only for meaning (green = fast/healthy, amber = healing, red = broken/old).
- Type: Inter for UI, JetBrains Mono for selectors, ms and $ values. Clear scale (about 12/14/16/20/28/40).
- 4px spacing grid, generous card padding, ≥16px side gutters on mobile.
- Must read well projected on a demo screen: big numbers, nothing tiny that matters.
- Design a dark variant of `Desktop / Healed result` if time allows (`Desktop Dark / Healed result`).

### Export (required: the code is built from these files)
When the design is approved, use the Paper MCP read tools to pull the design out of Paper into the repo:
1. `services/dashboard/design/exports/<frame-slug>.jsx`: the code Paper generates for each frame and for the Components frame (e.g. `desktop-healed.jsx`, `components.jsx`). Keep Paper's output as is; don't rewrite it.
2. `services/dashboard/design/screens/<frame-slug>.png`: a screenshot of each frame.
3. `services/dashboard/design/tokens.json`: every color, font family, font size/weight/line-height, radius, shadow and spacing value used on the canvas, in this shape:
   ```json
   {
     "color": { "surface": "#…", "ok": "#…", "heal": "#…", "fail": "#…", "diffOldBg": "#…", "diffOldFg": "#…", "diffNewBg": "#…", "diffNewFg": "#…", "...": "…" },
     "colorDark": { "...": "…" },
     "font": { "sans": "Inter, …", "mono": "JetBrains Mono, …" },
     "fontSize": { "xs": "12px", "...": "…" },
     "radius": { "...": "…" },
     "shadow": { "...": "…" },
     "space": { "...": "…" }
   }
   ```
4. `services/dashboard/design/NOTES.md`: a short list of anything the screenshots don't show, such as hover/animation behavior, the pulse timing, and what changes at the mobile breakpoint.

Then stop. The cloud session builds the React components from these exports.
