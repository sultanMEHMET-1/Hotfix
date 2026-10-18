import type { WorkflowSummary } from "@contracts/api_types";

export interface WorkflowPickerProps {
  workflows: WorkflowSummary[];
  selected: string;
  onSelect: (id: string) => void;
  disabled: boolean;
}

/** Choose which site's workflow to run: ruled tabs, the chosen one sits on the rule. Only shown when there is a choice. */
export default function WorkflowPicker({ workflows, selected, onSelect, disabled }: WorkflowPickerProps) {
  if (workflows.length < 2) return null;
  return (
    <div className="flex flex-wrap gap-x-6 border-b-[1.5px] border-line" role="group" aria-label="Workflow">
      {workflows.map((w) => (
        <button
          key={w.id}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(w.id)}
          aria-pressed={selected === w.id}
          title={w.goal}
          className={`-mb-[1.5px] min-h-[44px] border-b-[3px] px-1 font-mono text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
            selected === w.id ? "border-ink font-semibold text-ink" : "border-transparent text-ink-muted hover:text-ink"
          }`}
        >
          {w.id}
          {w.mutates && <span className="ml-2 rounded-panel border border-warning px-1.5 py-0.5 text-xs font-medium text-warning">writes</span>}
        </button>
      ))}
    </div>
  );
}
