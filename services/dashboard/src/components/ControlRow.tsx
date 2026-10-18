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
  workflows: WorkflowSummary[];
  workflowId: string;
  onWorkflowChange: (id: string) => void;
}

export default function ControlRow({ phase, result, scenario, onScenarioChange, onTrigger, mocksOn, workflows, workflowId, onWorkflowChange }: ControlRowProps) {
  const running = phase === "running-fast" || phase === "running-healing";
  const state = badgeState(phase, result);
  // While a run is in flight the previous result no longer describes it, so only the live label shows.
  const showPathLabel =
    state === "healing" || (!running && result !== null && (state === "healed" || state === "failed" || state === "fast"));

  return (
    <div className="mt-5 flex flex-col gap-4 pb-5 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-4 sm:gap-5">
        <button
          type="button"
          onClick={onTrigger}
          disabled={running}
          className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface transition-all hover:-translate-y-px hover:opacity-90 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
        >
          {running ? "Running" : "Trigger workflow"}
        </button>

        <StatusBadge state={state} label={phase === "error" ? "Request failed" : state === "failed" ? failedCopy(result) : undefined} />

        {showPathLabel && (
          <span className="text-xs text-ink-muted">{state === "healing" ? "Browser Use agent" : executionPathLabel(result!)}</span>
        )}
      </div>

      <WorkflowPicker workflows={workflows} selected={workflowId} onSelect={onWorkflowChange} disabled={running} />

      {!mocksOn && <ResetButton disabled={running} workflow={workflowId} />}

      {mocksOn && (
        <div className="flex items-center gap-1 rounded-lg border border-line bg-surface p-1">
          {SCENARIOS.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => onScenarioChange(s.value)}
              aria-pressed={scenario === s.value}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                scenario === s.value ? "bg-surface-subtle font-medium text-ink" : "text-ink-muted hover:text-ink"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
