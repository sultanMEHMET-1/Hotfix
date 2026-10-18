# Paper design prompt - Mender Dashboard

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
  diff?: { old_selector: string; new_selector: string } | null;
  recovery_attempted?: boolean;          // true = the Browser Use agent ran
  error?: { code: string; message: string } | null;
  heal_records?: HealRecord[];           // every selector the agent tried, one per field
  agent_cost_usd?: number | null;        // omitted = unknown; never show unknown as $0
  agent_duration_ms?: number | null;
}
// HealRecord: field, diff {old_selector, new_selector}, evidence (action_type, node_name,
// accessible_name, reasoning, …), verification_outcome "committed" | "rolled_back" | "rejected",
// version_before, version_after, rollback_version
```
The example responses are in `contracts/fixtures/workflow_success.json`, `workflow_healed.json` and `workflow_rolled_back.json`. Read them.
Use these realistic values in every frame:
- workflow: `permit-application`
- fast run (Deterministic Playwright): `125ms`, cost `$0.0000`
- healed run (Browser Use Agent Engaged): `4,200ms` total, of which agent time `3,100ms`, cost `$0.0020`
- heal records: `input_permit_id` `#permit-id` → `[data-testid='permit-id']` (committed, v1→v2); `submit_button` `#submit-btn` → `[data-action='lookup']` (committed, v2→v3), with evidence such as "click · BUTTON · Look up permit"
- rolled-back run: status failed, error `canary_mismatch`: "Canary output did not match; the baseline was restored as version 4.", both records `rolled_back`, cost **Unknown** (not reported)
- trace id: `0123456789abcdef0123456789abcdef`

### Frames to create (one canvas)
| Frame | Width | State |
| --- | --- | --- |
| `Desktop / Idle` | 1280 | Nothing run yet; benchmark cards show baseline numbers greyed; diff card empty state |
| `Desktop / Fast Path result` | 1280 | Green pill "Fast Path · Cached Selector", path label "Deterministic Playwright"; 125ms / $0.0000 highlighted; diff card says "No selector changes" |
| `Desktop / Healing (in progress)` | 1280 | Pulsing amber pill "Self-Healing Loop · Agent Re-indexing"; Trigger button in loading state; spinner/progress in the diff card |
| `Desktop / Healed result` | 1280 | Healed pill, path label "Browser Use Agent Engaged"; 4,200ms / $0.0020 highlighted against the fast baseline; both heal records shown as committed; Sentry button active |
| `Desktop / Rolled back` | 1280 | Red "Recovery failed · rolled back" state; the error message shown prominently; both heal records shown as rolled back (not applied) with the restored version; cost "Unknown" |
| `Mobile 390 / Healed result` | 390 | Same as `Desktop / Healed result`, single column, diff stacked old-over-new |
| `Components` | free | Every reusable piece with its states, side by side (see below) |

### Required regions, top to bottom
1. **Header**: "Mender" wordmark, workflow id chip `permit-application`, and a **Mocks ON/OFF** toggle on the right (a dev control, so keep it visually quiet).
2. **Control row**: primary **Trigger Workflow** button (calls `POST /api/v1/run-workflow`), the **status pill**, and a **mock scenario picker** with three options: Fast / Heal / Rollback (only shown when mocks are on).
3. **Benchmark cards**, 2-up:
   - *Execution time*: "Deterministic Playwright 125ms" vs "Browser Use Agent 4,200ms" (agent time 3,100ms as a secondary line), with a visual ratio (~34× slower).
   - *Cost*: "Cached Run $0.0000" vs "Agent Run $0.0020". Needs an "Unknown" variant for when cost isn't reported.
   Numbers are the hero; use a monospace face for them.
4. **Latency chart**: bar chart of the last ~10 runs (mix of ~300ms fast bars and ~12,000ms healed bars), colored by run type.
5. **Visual Diff Viewer** card: one row per heal record (there can be several). Each row shows the field name, then side-by-side panels: the left is red, labelled "Old selector" (e.g. `#submit-btn`); the right is green, labelled "Healed selector" (e.g. `[data-action='lookup']`). Each row has an outcome badge (committed / rolled back / rejected), the version change (v2 → v3), and an expandable "Why" line from the evidence ("click · BUTTON · Look up permit" plus the reasoning). Rolled-back rows must look clearly *not applied* (e.g. the green panel muted or struck through). Include an **Open Sentry trace ↗** button showing the trace id.
6. **Run log**: compact table with time, status, duration, cost and trace id.

### Components frame must include
- Status pill in four states: idle (neutral), fast path (green), self-healing (amber, show the pulse as a glow ring), healed (green with an amber "healed" badge), plus failed (red).
- Trigger button: default, hover, loading, disabled.
- Benchmark card, diff card (empty / populated), Sentry button (enabled / disabled with a "Sentry not configured" hint), run-log row (success / healed / failed), Mocks toggle, mock scenario picker (Fast / Heal / Rollback), heal-record row (committed / rolled back / rejected), error banner, path label (Deterministic Playwright / Browser Use Agent Engaged).

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
