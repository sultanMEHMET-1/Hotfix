import type { WorkflowSummary } from "@contracts/api_types";
import { workflowHint, workflowLabel } from "../lib/workflowLabel";
import Tooltip from "./Tooltip";

export interface WorkflowPickerProps {
  workflows: WorkflowSummary[];
  selected: string;
  onSelect: (id: string) => void;
  disabled: boolean;
}

/** Choose which site's workflow to run. The chosen one is filled ink. Only shown when there is a choice. */
export default function WorkflowPicker({ workflows, selected, onSelect, disabled }: WorkflowPickerProps) {
  if (workflows.length < 2) return null;
  return (
    <div className="flex w-full flex-col sm:w-auto sm:flex-row" role="group" aria-label="Workflow">
      {workflows.map((w) => {
        const on = selected === w.id;
        const hint = workflowHint(w.id);
        const button = (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSelect(w.id)}
            aria-pressed={on}
            className={`flex min-h-[44px] flex-1 items-center gap-2.5 border-[1.5px] border-ink px-4 font-display text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
              on ? "bg-ink font-semibold text-ground" : "bg-surface text-ink-muted hover:bg-surface-subtle hover:text-ink"
            }`}
          >
            {workflowLabel(w.id, w.goal)}
            {w.mutates && <span className={`font-sans text-sm ${on ? "text-ground" : "text-warning"}`}>writes</span>}
          </button>
        );
        const join = "-mt-[1.5px] first:mt-0 sm:-ml-[1.5px] sm:mt-0 sm:first:ml-0 sm:flex-none";
        return hint ? (
          <Tooltip key={w.id} label={hint} align="start" className={join}>{button}</Tooltip>
        ) : (
          <span key={w.id} className={`inline-flex ${join}`}>{button}</span>
        );
      })}
    </div>
  );
}
