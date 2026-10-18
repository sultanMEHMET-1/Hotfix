import type { WorkflowExecutionResponse, WorkflowSummary } from "@contracts/api_types";
import type { MockScenario } from "../api/mocks";
import { executionPathLabel } from "../lib/cost";
import type { RunPhase } from "../hooks/useWorkflowRun";
import ResetButton from "./ResetButton";
import Tooltip from "./Tooltip";
import WorkflowPicker from "./WorkflowPicker";
import StatusBadge, { badgeState, failedCopy } from "./StatusBadge";

const SCENARIOS: { value: MockScenario; label: string; hint: string }[] = [
  { value: "fast", label: "Fast", hint: "Cached run" },
  { value: "heal", label: "Heal", hint: "Agent repair" },
  { value: "rollback", label: "Rollback", hint: "Failed repair" },
];

export interface ControlRowProps {
  phase: RunPhase;
  result: WorkflowExecutionResponse | null;
  scenario: MockScenario;
  onScenarioChange: (s: MockScenario) => void;
  onTrigger: () => void;
  mocksOn: boolean;
  onToggleMocks: () => void;
  workflows: WorkflowSummary[];
  workflowId: string;
  onWorkflowChange: (id: string) => void;
  /** Called after the selected workflow's selectors were restored, so repairs listed on the page no longer apply. */
  onReset?: () => void;
  /** Editable inputs for the selected workflow (public sites only); the Trigger waits until none is empty. */
  inputs?: { name: string; label: string; value: string; example: string }[];
  onInputChange?: (name: string, value: string) => void;
  /** Create mode: only the picker and the Live switch show, since there is nothing to run yet. */
  creating?: boolean;
  onNew?: () => void;
  /** A created workflow is selected: offer to delete it. */
  onDelete?: () => void;
}

const SECONDARY =
  "min-h-[44px] rounded-panel border-[1.5px] border-ink bg-surface px-4 font-display text-sm transition-colors hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50";

export default function ControlRow({
  phase, result, scenario, onScenarioChange, onTrigger, mocksOn, onToggleMocks, workflows, workflowId, onWorkflowChange, onReset, inputs = [], onInputChange, creating = false, onNew, onDelete,
}: ControlRowProps) {
  const running = phase === "running-fast" || phase === "running-healing";
  const state = badgeState(phase, result);
  const output = !running && result && result.status !== "failed" && result.data ? Object.entries(result.data) : [];
  const missing = inputs.some((input) => input.value.trim() === "");
  // While a run is in flight the previous result no longer describes it, so only the live label shows.
  const showPathLabel =
    state === "healing" || (!running && result !== null && (state === "healed" || state === "failed" || state === "fast"));

  return (
    <section aria-label="Run controls" className="border-y-[1.5px] border-ink">
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3 border-b border-line py-3">
        <WorkflowPicker workflows={workflows} selected={workflowId} onSelect={onWorkflowChange} disabled={running} onNew={onNew} creating={creating} />

        <div className="flex flex-wrap items-center gap-3">
          <Tooltip label={mocksOn ? "Use real backend" : "Use sample data"} align="start">
            <button type="button" onClick={onToggleMocks} aria-pressed={!mocksOn}
              className={`${SECONDARY} ${!mocksOn ? "!bg-ink !text-ground" : ""}`}>
              Live
            </button>
          </Tooltip>
          {mocksOn ? (
            <div className="flex" role="group" aria-label="Mock scenario">
              {SCENARIOS.map((s) => (
                <Tooltip key={s.value} label={s.hint} className="-ml-[1.5px] first:ml-0">
                  <button
                    type="button"
                    onClick={() => onScenarioChange(s.value)}
                    aria-pressed={scenario === s.value}
                    className={`${SECONDARY} ${scenario === s.value ? "!bg-ink !text-ground" : ""}`}
                  >
                    {s.label}
                  </button>
                </Tooltip>
              ))}
            </div>
          ) : creating ? null : (
            <ResetButton disabled={running} workflow={workflowId} onReset={onReset} />
          )}
        </div>
      </div>

      {!creating && inputs.length > 0 && (
        <form
          aria-label="Workflow input"
          className="flex flex-col gap-4 border-b border-line py-4"
          onSubmit={(e) => { e.preventDefault(); if (!running && !missing) onTrigger(); }}
        >
          {inputs.map((input) => (
            <div key={input.name} className="flex max-w-[34rem] flex-col gap-1.5">
              <label htmlFor={`param-${input.name}`} className="text-sm text-ink-muted">{input.label}</label>
              <input
                id={`param-${input.name}`}
                type="text"
                value={input.value}
                maxLength={200}
                disabled={running}
                autoComplete="off"
                spellCheck={false}
                aria-describedby={`param-${input.name}-help`}
                aria-invalid={input.value.trim() === ""}
                onChange={(e) => onInputChange?.(input.name, e.target.value)}
                className="min-h-[48px] w-full rounded-panel border-[1.5px] border-ink bg-surface px-4 text-base text-ink disabled:opacity-60"
              />
              <span id={`param-${input.name}-help`} className={`text-sm ${input.value.trim() === "" ? "text-danger" : "text-ink-muted"}`}>
                {input.value.trim() === "" ? "Enter a value to run." : `Press Enter to run. Starts as ${input.example}.`}
              </span>
            </div>
          ))}
        </form>
      )}

      {!creating && <div className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:gap-8">
        <button
          type="button"
          onClick={onTrigger}
          disabled={running || missing}
          className="min-h-[60px] w-full rounded-panel border-[1.5px] border-ink bg-ink px-9 font-display text-lg text-ground transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {running ? "Running" : "Trigger workflow"}
        </button>

        <div className="flex flex-col gap-0.5">
          <StatusBadge state={state} label={phase === "error" ? "Request failed" : state === "failed" ? failedCopy(result) : undefined} />
          {showPathLabel && (
            <span className="text-sm text-ink-muted">{state === "healing" ? "Browser Use agent" : executionPathLabel(result!)}</span>
          )}
        </div>
        {onDelete && <button type="button" onClick={onDelete} disabled={running} className={`${SECONDARY} sm:ml-auto`}>Delete workflow</button>}
      </div>}

      {!creating && output.length > 0 && (
        <dl aria-label="Result" className="grid gap-x-8 gap-y-3 border-t border-line py-5 sm:grid-cols-[auto_1fr]">
          {output.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-sm text-ink-muted sm:pt-1">{key.replace(/_/g, " ")}</dt>
              <dd className="break-words font-mono text-lg text-ink">{typeof value === "string" ? value : JSON.stringify(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
