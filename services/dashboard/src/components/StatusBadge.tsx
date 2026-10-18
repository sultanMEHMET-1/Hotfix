import type { WorkflowExecutionResponse } from "@contracts/api_types";
import type { RunPhase } from "../hooks/useWorkflowRun";

export type BadgeState = "idle" | "fast" | "healing" | "healed" | "failed";

export function badgeState(phase: RunPhase, result: WorkflowExecutionResponse | null): BadgeState {
  if (phase === "running-fast") return "fast";
  if (phase === "running-healing") return "healing";
  if (phase === "error") return "failed";
  if (phase === "idle" || result === null) return "idle";
  if (result.status === "failed") return "failed";
  if (result.status === "healed") return "healed";
  return "fast";
}

/** What a failed run actually did, so the label never claims a revert that did not happen. */
export function failedCopy(result: WorkflowExecutionResponse | null): string {
  if (result?.error?.code === "rollback_failed") return "Rollback failed, operator action needed";
  if ((result?.heal_records ?? []).some((r) => r.verification_outcome === "rolled_back")) return "Reverted after a failed recovery";
  if (result?.recovery_attempted) return "Recovery failed, no selector changed";
  return "Run failed before recovery";
}

const COPY: Record<BadgeState, string> = {
  idle: "Idle",
  fast: "Fast path, cached selector",
  healing: "Agent is re-indexing the page",
  healed: "Healed, selector patched",
  failed: "Reverted after a failed recovery",
};

// A square ink marker, filled by meaning: green applied or fast, amber agent at work, oxblood failed.
const MARK: Record<BadgeState, string> = {
  idle: "border-ink-faint bg-transparent",
  fast: "border-success bg-success",
  healing: "border-warning bg-warning",
  healed: "border-success bg-success",
  failed: "border-danger bg-danger",
};

const TEXT: Record<BadgeState, string> = {
  idle: "text-ink-muted",
  fast: "text-ink",
  healing: "text-warning",
  healed: "text-ink",
  failed: "text-danger",
};

export default function StatusBadge({ state, label }: { state: BadgeState; label?: string }) {
  return (
    <div className="flex items-center gap-3" role="status">
      <span aria-hidden="true" className={`h-4 w-4 shrink-0 border-[1.5px] ${MARK[state]} ${state === "healing" ? "motion-safe:animate-pulse" : ""}`} />
      <span className={`font-display text-lg leading-tight ${TEXT[state]}`}>{label ?? COPY[state]}</span>
    </div>
  );
}
