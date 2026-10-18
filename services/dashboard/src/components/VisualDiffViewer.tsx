import type { WorkflowExecutionResponse } from "@contracts/api_types";
import type { RunPhase } from "../hooks/useWorkflowRun";
import Reveal from "./Reveal";
import SentryButton from "./SentryButton";
import HealRecordRow from "./HealRecordRow";

export interface VisualDiffViewerProps {
  phase: RunPhase;
  result: WorkflowExecutionResponse | null;
}

export default function VisualDiffViewer({ phase, result }: VisualDiffViewerProps) {
  const healing = phase === "running-healing";
  const records = healing ? [] : (result?.heal_records ?? []);

  return (
    <Reveal className="mt-4">
      <div className="rounded-xl border border-line bg-surface p-5">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs text-ink-muted">Visual diff viewer</span>
          <SentryButton traceId={healing ? null : (result?.trace_id ?? null)} />
        </div>

        {healing ? (
          <div className="mt-4 flex h-20 items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warning opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-warning" />
            </span>
            <span className="text-sm text-warning">Agent re-indexing the page, comparing against the live DOM</span>
          </div>
        ) : records.length === 0 ? (
          <div className="mt-4 flex h-20 items-center">
            <span className="text-sm text-ink-muted">
              {result === null ? "No runs yet" : "No selector changes — the cache is still fresh"}
            </span>
          </div>
        ) : (
          <div className="mt-2 flex flex-col">
            {records.map((r) => (
              <HealRecordRow key={r.field} record={r} />
            ))}
          </div>
        )}
      </div>
    </Reveal>
  );
}
