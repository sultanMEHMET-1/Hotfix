import type { WorkflowSummary } from "@contracts/api_types";
import { workflowHint, workflowLabel } from "../lib/workflowLabel";
import Tooltip from "./Tooltip";

export interface WorkflowPickerProps {
  workflows: WorkflowSummary[];
  selected: string;
  onSelect: (id: string) => void;
  disabled: boolean;
  /** Adds a final "+ New" button that opens the create-from-a-sentence mode; pressed while that mode is open. */
  onNew?: () => void;
  creating?: boolean;
}

/** Choose which site's workflow to run. The chosen one is filled ink. Only shown when there is a choice. */
export default function WorkflowPicker({ workflows, selected, onSelect, disabled, onNew, creating = false }: WorkflowPickerProps) {
  if (workflows.length < 2) return null;
  return (
    <div className="flex w-full flex-col sm:w-auto sm:flex-row" role="group" aria-label="Workflow">
      {workflows.map((w) => {
        const on = !creating && selected === w.id;
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
      {onNew && (
        <Tooltip label="Create from a sentence" align="start" className="-mt-[1.5px] sm:-ml-[1.5px] sm:mt-0 sm:flex-none">
          <button
            type="button"
            disabled={disabled}
            onClick={onNew}
            aria-pressed={creating}
            className={`flex min-h-[44px] w-full flex-1 items-center border-[1.5px] border-ink px-4 font-display text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
              creating ? "bg-ink font-semibold text-ground" : "bg-surface text-ink-muted hover:bg-surface-subtle hover:text-ink"
            }`}
          >
            + New
          </button>
        </Tooltip>
      )}
    </div>
  );
}
