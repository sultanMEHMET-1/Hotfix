import type { RunHistoryEntry } from "../hooks/useWorkflowRun";
import { formatMs, formatUsd } from "../lib/format";

const STATUS_MARK: Record<string, string> = {
  success: "border-success bg-success",
  healed: "border-warning bg-warning",
  failed: "border-danger bg-danger",
};

const STATUS_TEXT: Record<string, string> = {
  success: "text-success",
  healed: "text-warning",
  failed: "text-danger",
};

const HEAD = "px-3 pb-3 text-left text-sm font-medium text-ink-muted";

export default function RunLog({ history }: { history: RunHistoryEntry[] }) {
  return (
    <section aria-labelledby="runlog-title" className="mt-14">
      <h2 id="runlog-title" className="text-xl">Run log</h2>
      <div className="scrollbar-slim mt-5 overflow-x-auto">
        <table className="w-full border-collapse text-base">
          <thead>
            <tr className="border-b-[3px] border-double border-ink">
              <th scope="col" className={HEAD}>Time</th>
              <th scope="col" className={HEAD}>Status</th>
              <th scope="col" className={HEAD}>Duration</th>
              <th scope="col" className={HEAD}>Cost</th>
              <th scope="col" className={`${HEAD} hidden sm:table-cell`}>Trace</th>
            </tr>
          </thead>
          <tbody>
            {history.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-base text-ink-muted">
                  No runs recorded yet
                </td>
              </tr>
            ) : (
              history.map((entry) => (
                <tr key={entry.id} className="border-b border-line last:border-b-0">
                  <td className="whitespace-nowrap px-3 py-3 font-mono text-sm tabular-nums">
                    {new Date(entry.startedAt).toLocaleTimeString("en-US", { hour12: false })}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3">
                    <span className={`inline-flex items-center gap-2 text-base ${STATUS_TEXT[entry.response.status] ?? "text-ink-muted"}`}>
                      <span aria-hidden="true" className={`h-3 w-3 border-[1.5px] ${STATUS_MARK[entry.response.status] ?? "border-ink-faint"}`} />
                      {entry.response.status}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 font-mono text-sm tabular-nums">
                    {formatMs(entry.response.execution_time_ms)}
                  </td>
                  <td className={`whitespace-nowrap px-3 py-3 font-mono text-sm tabular-nums ${entry.costUsd === null ? "italic text-ink-muted" : ""}`}>
                    {formatUsd(entry.costUsd)}
                  </td>
                  <td className="hidden truncate px-3 py-3 font-mono text-sm text-ink-muted sm:table-cell">{entry.response.trace_id}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
