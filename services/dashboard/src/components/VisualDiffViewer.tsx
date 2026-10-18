import type { WorkflowExecutionResponse } from "@contracts/api_types";
import type { RunHistoryEntry, RunPhase } from "../hooks/useWorkflowRun";
import { useElapsed } from "../hooks/useElapsed";
import { sentryTraceUrl } from "../lib/sentry";
import SentryButton from "./SentryButton";
import HealRecordRow from "./HealRecordRow";

export interface VisualDiffViewerProps {
  phase: RunPhase;
  result: WorkflowExecutionResponse | null;
  /** Every run so far, newest first; the corrections of the selected workflow's runs pile up below. */
  history: RunHistoryEntry[];
  workflowId: string;
  /** Corrections from runs started before this time are hidden (cleared, or undone by a selector reset). */
  since: number;
  onClear: () => void;
}

const SECONDARY = "min-h-[44px] rounded-panel border-[1.5px] border-ink bg-surface px-4 font-display text-sm transition-colors hover:bg-surface-subtle";

/** The correction log: every repair this session, newest first, each applied or struck out. A run with no changes adds nothing and removes nothing. */
export default function VisualDiffViewer({ phase, result, history, workflowId, since, onClear }: VisualDiffViewerProps) {
  const healing = phase === "running-healing";
  const failedRequest = phase === "error";
  const elapsed = useElapsed(healing);
  const groups = history.filter((h) => h.workflowId === workflowId && h.startedAt > since && (h.response.heal_records?.length ?? 0) > 0);
  const latestChangedNothing = !healing && !failedRequest && result !== null && (result.heal_records?.length ?? 0) === 0 && result.status !== "failed";

 if (groups.length === 0 && !healing && !failedRequest && result === null) return null;

  return (
    <section aria-labelledby="corrections-title" className="mt-14">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <h2 id="corrections-title" className="text-xl">Corrections</h2>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          {groups.length > 0 && <button type="button" onClick={onClear} className={SECONDARY}>Clear corrections</button>}
          <SentryButton traceId={healing ? null : (result?.trace_id ?? null)} />
        </div>
      </div>

      {healing && (
        <div className="mt-5 flex flex-col gap-3 rounded-panel border-[1.5px] border-dashed border-warning bg-warning-bg p-6 sm:flex-row sm:items-center sm:gap-8">
          <span className="font-mono text-[clamp(2.75rem,6vw,4.25rem)] font-medium leading-none tabular-nums text-warning" aria-hidden="true">
            {(elapsed / 1000).toFixed(1)}
            <span className="ml-1 text-lg">s</span>
          </span>
          <span className="text-base text-warning">Agent re-indexing the page, comparing against the live DOM</span>
        </div>
      )}

      {groups.length === 0 && !healing && (
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
      )}

      {groups.length > 0 && latestChangedNothing && (
        <p className="mt-5 text-base text-ink-muted">The latest run used the cache and changed nothing. Earlier corrections stay below.</p>
      )}

      {groups.map((entry) => {
        const traceUrl = sentryTraceUrl(entry.response.trace_id);
        return (
          <div key={entry.id} className="mt-6" role="group" aria-label={`Corrections from the run at ${new Date(entry.startedAt).toLocaleTimeString("en-US", { hour12: false })}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h3 className="font-mono text-base font-medium tabular-nums">
                {new Date(entry.startedAt).toLocaleTimeString("en-US", { hour12: false })}
                <span className="ml-3 font-sans text-sm font-normal text-ink-muted">{entry.response.status}</span>
              </h3>
              {traceUrl && (
                <a href={traceUrl} target="_blank" rel="noreferrer" className="text-sm text-ink underline decoration-2 underline-offset-4">View trace</a>
              )}
            </div>
            <ul className="mt-3 list-none border-y-[1.5px] border-ink p-0">
              {(entry.response.heal_records ?? []).map((r, i) => (
                <HealRecordRow key={`${entry.id}:${r.field}`} record={r} index={i} />
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
