import type { HealRecord } from "@contracts/api_types";

const OUTCOME_LABEL: Record<HealRecord["verification_outcome"], string> = {
  committed: "Committed",
  rolled_back: "Rolled back",
  rejected: "Rejected",
};

const OUTCOME_BADGE: Record<HealRecord["verification_outcome"], string> = {
  committed: "bg-success-bg text-success",
  rolled_back: "bg-danger-bg text-danger",
  rejected: "bg-surface-subtle text-ink-muted",
};

export default function HealRecordRow({ record }: { record: HealRecord }) {
  const applied = record.verification_outcome === "committed";
  const versionLabel =
    record.verification_outcome === "committed"
      ? `v${record.version_before} → v${record.version_after ?? record.version_before}`
      : record.verification_outcome === "rolled_back"
        ? `v${record.version_before}, restored to v${record.rollback_version ?? record.version_before}`
        : `v${record.version_before}, never installed`;

  return (
    <div className="flex flex-col gap-3 border-t border-line py-5 first:border-t-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-sm text-ink">{record.field}</span>
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-xs text-ink-faint">{versionLabel}</span>
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${OUTCOME_BADGE[record.verification_outcome]}`}>
            {OUTCOME_LABEL[record.verification_outcome]}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 rounded-lg bg-surface-subtle p-3 sm:grid-cols-2 sm:gap-6">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-ink-faint">Old selector</span>
          <span className="font-mono text-sm text-danger">{record.diff.old_selector}</span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-ink-faint">{applied ? "New selector" : "Proposed selector"}</span>
          <span className={`font-mono text-sm ${applied ? "text-success" : "text-ink-muted line-through"}`}>
            {record.diff.new_selector}
          </span>
        </div>
      </div>
      <details className="group text-xs text-ink-muted">
        <summary className="inline-flex cursor-pointer select-none items-center gap-1 marker:content-none hover:text-ink">
          <span className="inline-block transition-transform duration-200 group-open:rotate-90">&rsaquo;</span>
          Why
        </summary>
        <p className="mt-1.5 animate-fade-in pl-3">
          {record.evidence.action_type} on {record.evidence.node_name}
          {record.evidence.accessible_name ? `, "${record.evidence.accessible_name}"` : ""}. {record.evidence.reasoning}
        </p>
      </details>
    </div>
  );
}
