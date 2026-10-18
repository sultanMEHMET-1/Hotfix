import type { HealRecord } from "@contracts/api_types";
import ScrollReveal from "./ScrollReveal";

const OUTCOME_LABEL: Record<HealRecord["verification_outcome"], string> = {
  committed: "Committed",
  rolled_back: "Rolled back",
  rejected: "Rejected",
};

const STAMP: Record<HealRecord["verification_outcome"], string> = {
  committed: "border-success text-success",
  rolled_back: "border-danger text-danger",
  rejected: "border-ink-muted text-ink-muted",
};

const VERB: Record<string, string> = { input: "typed into", click: "clicked", read: "read" };

/** One plain sentence for what the agent did, built from the evidence. The backend's reasoning stays in the API and Sentry. */
function evidenceLine(evidence: HealRecord["evidence"]): string {
  const verb = VERB[evidence.action_type] ?? evidence.action_type;
  const node = evidence.node_name.toLowerCase();
  return evidence.accessible_name ? `Agent ${verb} ${evidence.accessible_name} (${node}).` : `Agent ${verb} a ${node}.`;
}

/**
 * One correction as a diff. A change that was applied is printed: filled paper, the old selector struck out,
 * the new one in bold green. One that was not applied is only drawn: dashed rules, no fill, the selector that
 * still stands in plain ink and the refused proposal struck through.
 */
export default function HealRecordRow({ record, index = 0 }: { record: HealRecord; index?: number }) {
  const outcome = record.verification_outcome;
  const applied = outcome === "committed";
  const versionLabel =
    outcome === "committed"
      ? `v${record.version_before} → v${record.version_after ?? record.version_before}`
      : outcome === "rolled_back"
        ? `v${record.version_before}, restored to v${record.rollback_version ?? record.version_before}`
        : `v${record.version_before}, never installed`;
  const note = applied
    ? evidenceLine(record.evidence)
    : `Not applied. ${outcome === "rejected" ? "Refused before it was written. " : "The original selector stands. "}${evidenceLine(record.evidence)}`;

  return (
    <ScrollReveal
      as="li"
      delay={index * 0.06}
      className={`grid gap-x-8 gap-y-3 border-b px-1 py-6 last:border-b-0 sm:px-5 md:grid-cols-[13rem_minmax(0,1fr)_auto] ${
        applied ? "border-line bg-surface" : "border-dashed border-ink-faint"
      }`}
    >
      <div data-outcome={outcome} className="contents">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-base font-medium">{record.field}</span>
          <span className="font-mono text-sm text-ink-muted">{versionLabel}</span>
        </div>

        <div className="flex min-w-0 flex-col gap-1.5">
          <p className="flex gap-3 font-mono text-base">
            <span aria-hidden="true" className="w-3 shrink-0 text-ink-muted">{applied ? "-" : "="}</span>
            <span className="sr-only">Old selector</span>
            <span className={`break-all ${applied ? "text-danger line-through decoration-2" : "font-medium text-ink"}`}>{record.diff.old_selector}</span>
          </p>
          <p className="flex gap-3 font-mono text-base">
            <span aria-hidden="true" className="w-3 shrink-0 text-ink-muted">+</span>
            <span className="sr-only">{applied ? "New selector" : "Proposed selector"}</span>
            <span className={`break-all ${applied ? "font-semibold text-success" : "text-ink-muted line-through decoration-2"}`}>{record.diff.new_selector}</span>
          </p>
          <p className="mt-1 text-sm text-ink-muted">{note}</p>
        </div>

        <div className="md:justify-self-end">
          <span className={`inline-block rounded-panel border-2 px-3 py-1 font-mono text-sm font-semibold uppercase tracking-wider ${STAMP[outcome]}`}>
            {OUTCOME_LABEL[outcome]}
          </span>
        </div>
      </div>
    </ScrollReveal>
  );
}
