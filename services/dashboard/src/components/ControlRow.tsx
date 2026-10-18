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
    <section aria-label="Run controls" className="border-y-[1.5px] border-ink">
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3 border-b border-line py-3">
        <WorkflowPicker workflows={workflows} selected={workflowId} onSelect={onWorkflowChange} disabled={running} />

        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={onToggleMocks} aria-pressed={mocksOn} title="Filled: canned demo responses, no backend needed. Outlined: the real backend."
            className={`${SECONDARY} ${mocksOn ? "!bg-ink !text-ground" : ""}`}>
            Demo
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
        </div>
      </div>

      <div className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:gap-8">
        <button
          type="button"
          onClick={onTrigger}
          disabled={running}
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
      </div>
    </section>
  );
}
