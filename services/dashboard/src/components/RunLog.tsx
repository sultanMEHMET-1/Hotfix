import type { RunHistoryEntry } from "../hooks/useWorkflowRun";
import { formatMs, formatUsd } from "../lib/format";
import Reveal from "./Reveal";

const STATUS_BADGE: Record<string, string> = {
  success: "bg-success-bg text-success",
  healed: "bg-warning-bg text-warning",
  failed: "bg-danger-bg text-danger",
};

const STATUS_DOT: Record<string, string> = {
  success: "bg-success",
  healed: "bg-warning",
  failed: "bg-danger",
};

export default function RunLog({ history }: { history: RunHistoryEntry[] }) {
  return (
    <Reveal className="my-4">
      <div className="rounded-xl border border-line bg-surface p-5">
        <span className="text-xs text-ink-muted">Run log</span>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className="px-2 pb-2.5 text-left text-xs font-medium uppercase tracking-wide text-ink-faint">Time</th>
                <th className="px-2 pb-2.5 text-left text-xs font-medium uppercase tracking-wide text-ink-faint">Status</th>
                <th className="px-2 pb-2.5 text-left text-xs font-medium uppercase tracking-wide text-ink-faint">Duration</th>
                <th className="px-2 pb-2.5 text-left text-xs font-medium uppercase tracking-wide text-ink-faint">Cost</th>
                <th className="px-2 pb-2.5 text-left text-xs font-medium uppercase tracking-wide text-ink-faint">Trace</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-sm text-ink-muted">
                    No runs recorded yet
                  </td>
                </tr>
              ) : (
                history.map((entry, i) => (
                  <tr
                    key={entry.id}
                    style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}
                    className="animate-fade-up border-b border-line transition-colors last:border-b-0 hover:bg-surface-subtle"
                  >
                    <td className="whitespace-nowrap px-2 py-3 font-mono text-xs text-ink">
                      {new Date(entry.startedAt).toLocaleTimeString("en-US", { hour12: false })}
                    </td>
                    <td className="whitespace-nowrap px-2 py-3">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ${
                          STATUS_BADGE[entry.response.status] ?? "text-ink-muted"
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[entry.response.status] ?? "bg-ink-faint"}`} />
                        {entry.response.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-2 py-3 font-mono text-xs tabular-nums text-ink">
                      {formatMs(entry.response.execution_time_ms)}
                    </td>
                    <td
                      className={`whitespace-nowrap px-2 py-3 font-mono text-xs tabular-nums ${
                        entry.costUsd === null ? "italic text-ink-faint" : "text-ink"
                      }`}
                    >
                      {formatUsd(entry.costUsd)}
                    </td>
                    <td className="truncate px-2 py-3 font-mono text-xs text-ink-faint">{entry.response.trace_id}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Reveal>
  );
}
