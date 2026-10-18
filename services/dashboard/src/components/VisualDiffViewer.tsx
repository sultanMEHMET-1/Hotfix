import type { WorkflowExecutionResponse } from "@contracts/api_types";
import type { RunPhase } from "../hooks/useWorkflowRun";
import { useElapsed } from "../hooks/useElapsed";
import SentryButton from "./SentryButton";
import HealRecordRow from "./HealRecordRow";

export interface VisualDiffViewerProps {
  phase: RunPhase;
  result: WorkflowExecutionResponse | null;
}

/** The correction log: what the agent changed, and whether it was applied or struck out. */
export default function VisualDiffViewer({ phase, result }: VisualDiffViewerProps) {
  const healing = phase === "running-healing";
  const failedRequest = phase === "error";
  const records = healing || failedRequest ? [] : (result?.heal_records ?? []);
  const elapsed = useElapsed(healing);

  return (
    <section aria-labelledby="corrections-title" className="mt-14">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <h2 id="corrections-title" className="text-xl">Corrections</h2>
        <SentryButton traceId={healing ? null : (result?.trace_id ?? null)} />
      </div>

      {healing ? (
        <div className="mt-5 flex flex-col gap-3 rounded-panel border-[1.5px] border-dashed border-warning bg-warning-bg p-6 sm:flex-row sm:items-center sm:gap-8">
          <span className="font-mono text-[clamp(2.75rem,6vw,4.25rem)] font-medium leading-none tabular-nums text-warning" aria-hidden="true">
            {(elapsed / 1000).toFixed(1)}
            <span className="ml-1 text-lg">s</span>
          </span>
          <span className="text-base text-warning">Agent re-indexing the page, comparing against the live DOM</span>
        </div>
      ) : records.length === 0 ? (
        <p className="mt-5 border-y-[1.5px] border-line py-8 text-base text-ink-muted">
          {failedRequest
            ? "The request did not complete. See the message above."
            : result === null
              ? "No runs yet"
              : result.error?.code === "rollback_failed"
                ? "Rollback failed. Restore the selectors before running again."
                : result.status === "failed"
                  ? "No selector was changed. Recovery did not complete."
                  : "No selector changes. The cache is still fresh."}
        </p>
      ) : (
        <ul className="mt-5 list-none border-y-[1.5px] border-ink p-0">
          {records.map((r, i) => (
            <HealRecordRow key={r.field} record={r} index={i} />
          ))}
        </ul>
      )}
    </section>
  );
}
