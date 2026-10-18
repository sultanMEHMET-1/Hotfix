import type { WorkflowSummary } from "@contracts/api_types";

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
        return (
          <button
            key={w.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(w.id)}
            aria-pressed={on}
            title={w.goal}
            className={`-mt-[1.5px] flex min-h-[44px] items-center gap-2.5 border-[1.5px] border-ink px-4 font-mono text-sm first:mt-0 sm:-ml-[1.5px] sm:mt-0 sm:first:ml-0 disabled:cursor-not-allowed disabled:opacity-50 ${
              on ? "bg-ink font-semibold text-ground" : "bg-surface text-ink-muted hover:bg-surface-subtle hover:text-ink"
            }`}
          >
            {w.id}
            {w.mutates && <span className={`font-sans text-sm italic ${on ? "text-ground" : "text-warning"}`}>writes</span>}
          </button>
        );
      })}
    </div>
  );
}
