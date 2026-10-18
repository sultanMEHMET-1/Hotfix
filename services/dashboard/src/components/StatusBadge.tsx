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

const DOT: Record<BadgeState, string> = {
  idle: "bg-ink-faint",
  fast: "bg-success",
  healing: "bg-warning",
  healed: "bg-success",
  failed: "bg-danger",
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
    <div
      className="inline-flex items-center gap-2 rounded-md border border-line bg-surface py-1 pl-1.5 pr-3 transition-colors"
      role="status"
    >
      <span className="relative flex h-2 w-2">
        {state === "healing" && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${DOT[state]}`} />}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${DOT[state]}`} />
      </span>
      <span className={`text-sm font-medium ${TEXT[state]}`}>{label ?? COPY[state]}</span>
      {state === "healed" && (
        <span className="rounded-sm bg-warning-bg px-1.5 py-0.5 text-[10px] font-semibold text-warning">healed</span>
      )}
    </div>
  );
}
