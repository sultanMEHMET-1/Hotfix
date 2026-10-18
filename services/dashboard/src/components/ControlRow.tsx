import type { WorkflowExecutionResponse, WorkflowSummary } from "@contracts/api_types";
import type { MockScenario } from "../api/mocks";
import { executionPathLabel } from "../lib/cost";
import type { RunPhase } from "../hooks/useWorkflowRun";
import ResetButton from "./ResetButton";
import WorkflowPicker from "./WorkflowPicker";
import StatusBadge, { badgeState, failedCopy } from "./StatusBadge";

const SCENARIOS: { value: MockScenario; label: string }[] = [
  { value: "fast", label: "Fast" },
  { value: "heal", label: "Heal" },
  { value: "rollback", label: "Rollback" },
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
}

const SECONDARY =
  "min-h-[44px] rounded-panel border-[1.5px] border-ink bg-surface px-4 font-display text-sm transition-colors hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50";

export default function ControlRow({
  phase, result, scenario, onScenarioChange, onTrigger, mocksOn, onToggleMocks, workflows, workflowId, onWorkflowChange,
}: ControlRowProps) {
  const running = phase === "running-fast" || phase === "running-healing";
  const state = badgeState(phase, result);
  // While a run is in flight the previous result no longer describes it, so only the live label shows.
  const showPathLabel =
    state === "healing" || (!running && result !== null && (state === "healed" || state === "failed" || state === "fast"));

  return (
    <>
      <WorkflowPicker workflows={workflows} selected={workflowId} onSelect={onWorkflowChange} disabled={running} />

      <section aria-label="Run" className="mt-8 flex flex-col gap-5 sm:flex-row sm:items-center sm:gap-8">
        <button
          type="button"
          onClick={onTrigger}
          disabled={running}
          className="min-h-[60px] w-full rounded-panel border-[1.5px] border-ink bg-ink px-9 font-display text-lg text-ground shadow-[3px_3px_0_rgb(var(--color-ground)),6px_6px_0_rgb(var(--color-ink))] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 active:translate-x-0 active:translate-y-0 active:shadow-none disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none disabled:hover:translate-x-0 disabled:hover:translate-y-0 sm:w-auto"
        >
          {running ? "Running" : "Trigger workflow"}
        </button>

        <div className="flex flex-col gap-1">
          <StatusBadge state={state} label={phase === "error" ? "Request failed" : state === "failed" ? failedCopy(result) : undefined} />
          {showPathLabel && (
            <span className="pl-7 text-sm text-ink-muted">{state === "healing" ? "Browser Use agent" : executionPathLabel(result!)}</span>
          )}
        </div>
      </section>

      <fieldset className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-panel border border-dashed border-ink-faint px-4 pb-3 pt-1">
        <legend className="px-2 text-sm text-ink-muted">Demo controls</legend>
        <button type="button" onClick={onToggleMocks} aria-pressed={mocksOn} title="Switch between mocked demo responses and the real backend"
          className={`${SECONDARY} ${mocksOn ? "!bg-ink !text-ground" : ""}`}>
          Mocks {mocksOn ? "on" : "off"}
        </button>
        {mocksOn ? (
          <div className="flex" role="group" aria-label="Mock scenario">
            {SCENARIOS.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => onScenarioChange(s.value)}
                aria-pressed={scenario === s.value}
                className={`${SECONDARY} -ml-[1.5px] first:ml-0 ${scenario === s.value ? "!bg-ink !text-ground" : ""}`}
              >
                {s.label}
              </button>
            ))}
          </div>
        ) : (
          <ResetButton disabled={running} workflow={workflowId} />
        )}
      </fieldset>
    </>
  );
}
