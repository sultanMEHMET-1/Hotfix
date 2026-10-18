import type { HealRecord } from "@contracts/api_types";

const OUTCOME_LABEL: Record<HealRecord["verification_outcome"], string> = {
  committed: "Committed",
  rolled_back: "Rolled back",
  rejected: "Rejected",
};

// An applied correction is printed: solid rules, a flat offset, a green stamp. One that was not applied is
// drawn but never inked: dashed rules, no offset, so it can never be mistaken for the live selector.
const FRAME: Record<HealRecord["verification_outcome"], string> = {
  committed: "printed animate-stamp",
  rolled_back: "rounded-panel border-[1.5px] border-dashed border-ink-muted bg-surface",
  rejected: "rounded-panel border-[1.5px] border-dotted border-ink-faint bg-surface",
};

const STAMP: Record<HealRecord["verification_outcome"], string> = {
  committed: "border-success text-success",
  rolled_back: "border-danger text-danger",
  rejected: "border-ink-muted text-ink-muted",
};

const NOTE: Partial<Record<HealRecord["verification_outcome"], string>> = {
  rolled_back: "Not applied. The original selector stands.",
  rejected: "Not applied. This candidate was refused before it was written.",
};

export default function HealRecordRow({ record }: { record: HealRecord }) {
  const outcome = record.verification_outcome;
  const applied = outcome === "committed";
  const versionLabel =
    outcome === "committed"
      ? `v${record.version_before} → v${record.version_after ?? record.version_before}`
      : outcome === "rolled_back"
        ? `v${record.version_before}, restored to v${record.rollback_version ?? record.version_before}`
        : `v${record.version_before}, never installed`;

  return (
    <li className={`flex flex-col gap-4 p-5 sm:p-6 ${FRAME[outcome]}`} data-outcome={outcome}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-mono text-base font-medium">{record.field}</span>
        <div className="flex flex-wrap items-center gap-4">
          <span className="font-mono text-sm text-ink-muted">{versionLabel}</span>
          <span className={`rounded-panel border-2 px-3 py-1 font-mono text-sm font-semibold uppercase tracking-wider ${STAMP[outcome]}`}>
            {OUTCOME_LABEL[outcome]}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-8">
        <div className="flex flex-col gap-1">
          <span className="text-sm text-ink-muted">Old selector</span>
          <span className={`break-all font-mono text-base ${applied ? "text-danger line-through decoration-2" : "font-medium text-ink"}`}>
            {record.diff.old_selector}
          </span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-sm text-ink-muted">{applied ? "New selector" : "Proposed selector"}</span>
          <span className={`break-all font-mono text-base ${applied ? "font-semibold text-success" : "text-ink-muted line-through decoration-2"}`}>
            {record.diff.new_selector}
          </span>
        </div>
      </div>

      {NOTE[outcome] && <p className="text-sm italic text-ink-muted">{NOTE[outcome]}</p>}

      <details className="group text-sm text-ink-muted">
        <summary className="inline-flex min-h-[44px] cursor-pointer select-none items-center gap-2 italic marker:content-none hover:text-ink">
          <span aria-hidden="true" className="inline-block transition-transform duration-200 group-open:rotate-90">&rsaquo;</span>
          Why
        </summary>
        <p className="max-w-[68ch] pb-1 pl-5 leading-relaxed">
          {record.evidence.action_type} on {record.evidence.node_name}
          {record.evidence.accessible_name ? `, "${record.evidence.accessible_name}"` : ""}. {record.evidence.reasoning}
        </p>
      </details>
    </li>
  );
}
