import type { WorkflowSummary } from "@contracts/api_types";

export interface WorkflowPickerProps {
  workflows: WorkflowSummary[];
  selected: string;
  onSelect: (id: string) => void;
  disabled: boolean;
}

/** Choose which site's workflow to run. Only shown when the backend offers more than one. */
export default function WorkflowPicker({ workflows, selected, onSelect, disabled }: WorkflowPickerProps) {
  if (workflows.length < 2) return null;
  return (
    <div className="flex items-center gap-1 rounded-lg border border-line bg-surface p-1" role="group" aria-label="Workflow">
      {workflows.map((w) => (
        <button
          key={w.id}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(w.id)}
          aria-pressed={selected === w.id}
          title={w.goal}
          className={`rounded-md px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
            selected === w.id ? "bg-surface-subtle font-medium text-ink" : "text-ink-muted hover:text-ink"
          }`}
        >
          {w.id}
          {w.mutates && <span className="ml-1.5 rounded-sm bg-warning-bg px-1 py-0.5 text-[10px] font-semibold text-warning">writes</span>}
        </button>
      ))}
    </div>
  );
}
