import type { Benchmarks } from "../hooks/useWorkflowRun";
import { formatDurationParts, formatUsd } from "../lib/format";

export interface BenchmarkSummaryProps {
  benchmarks: Benchmarks;
  /** True while the figures are fixture baselines rather than a real run, so they are never passed off as measured. */
  sample?: boolean;
}

/** What an agent doing the task costs per run, from our model benchmark (about 11 s, half a cent). Used only until a real agent run exists. */
const AGENT_EVERY_RUN_MS = 11000;

export default function BenchmarkSummary({ benchmarks, sample = false }: BenchmarkSummaryProps) {
  const { fastMs, healMs } = benchmarks;
  // The agent side is a real run of this workflow in this session when there is one, else the benchmark figure.
  const agentMs = healMs ?? AGENT_EVERY_RUN_MS;
  const ratio = fastMs !== null && fastMs > 0 ? agentMs / fastMs : null;
  // Both bars share one scale, so the picture is the same as the numbers: the agent run is the long one.
  const scale = Math.max(fastMs ?? 0, healMs ?? 0);
  const pct = (ms: number | null) => (ms === null || scale === 0 ? null : Math.max((ms / scale) * 100, 2));

  return (
    <section aria-labelledby="measure-title" className="mt-12">
      <h2 id="measure-title" className="text-xl">Cached run against the agent</h2>
      <div className="mt-5 grid border-y-[1.5px] border-ink md:grid-cols-[1fr_1fr_minmax(0,0.8fr)]">
        <Measure label="Fast replay" ms={fastMs} width={pct(fastMs)} tone="success" />
        <Measure label="Agent re-indexing" ms={healMs} width={pct(healMs)} tone="warning" cost={benchmarks.healCost} showCost />
        <div className="flex flex-col justify-center border-t-[1.5px] border-ink px-1 py-6 md:border-l-[1.5px] md:border-t-0 md:px-8">
          <span className="font-display text-hero text-ink">{ratio !== null ? `${Math.round(ratio)}×` : "n/a"}</span>
          <span className="mt-3 text-sm text-ink-muted">{ratio !== null ? "faster than an agent on every run" : "Run it once to compare"}</span>
          {ratio !== null && (
            <span className="mt-1 text-sm text-ink-muted">
              {healMs !== null ? "Against the agent run you just measured." : "Agent every run: about 11 s and half a cent, from our benchmark."}
            </span>
          )}
        </div>
      </div>
      {sample && <p className="mt-3 text-sm text-ink-muted">Sample figures from fixtures. Run the workflow for measured numbers.</p>}
    </section>
  );
}

const BAR: Record<"success" | "warning", string> = { success: "bg-success", warning: "bg-warning" };

function Measure({ label, ms, width, tone, cost = null, showCost = false }: {
  label: string; ms: number | null; width: number | null; tone: "success" | "warning"; cost?: number | null; showCost?: boolean;
}) {
  const { value, unit } = ms === null ? { value: "n/a", unit: "" } : formatDurationParts(ms);
  return (
    <div className="px-1 py-6 md:px-8 md:first:pl-0 [&:nth-child(2)]:border-t-[1.5px] [&:nth-child(2)]:border-ink md:[&:nth-child(2)]:border-l-[1.5px] md:[&:nth-child(2)]:border-t-0">
      <div className="text-sm text-ink-muted">{label}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={`font-mono font-medium tabular-nums text-ink ${ms === null ? "text-lg text-ink-muted" : "text-[clamp(2.75rem,6vw,4.25rem)] leading-none"}`}>
          {value}
        </span>
        <span className="font-mono text-base text-ink-muted">{unit}</span>
      </div>
      <div
        className={`mt-4 h-4 border-[1.5px] ${width === null ? "border-dashed border-ink-faint" : "border-ink"}`}
        role="img"
        aria-label={ms === null ? `${label}: no run yet` : `${label}: ${value} ${unit}`}
      >
        {width !== null && <div className={`h-full ${BAR[tone]}`} style={{ width: `${width}%` }} />}
      </div>
      {showCost && (
        <>
          <div className="mt-5 text-sm text-ink-muted">Agent cost</div>
          <div className={`mt-1 font-mono tabular-nums ${cost === null ? "text-base text-ink-muted" : "text-xl font-medium text-ink"}`}>
            {formatUsd(cost)}
          </div>
        </>
      )}
    </div>
  );
}
