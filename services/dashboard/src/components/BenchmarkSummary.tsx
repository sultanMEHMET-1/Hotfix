import type { Benchmarks } from "../hooks/useWorkflowRun";
import { formatMsParts, formatUsd } from "../lib/format";

export interface BenchmarkSummaryProps {
  benchmarks: Benchmarks;
  /** True while the figures are fixture baselines rather than a real run, so they are never passed off as measured. */
  sample?: boolean;
}

export default function BenchmarkSummary({ benchmarks, sample = false }: BenchmarkSummaryProps) {
  const { fastMs, healMs } = benchmarks;
  const ratio = fastMs !== null && healMs !== null && fastMs > 0 ? healMs / fastMs : null;
  // Both bars share one scale, so the picture is the same as the numbers: the agent run is the long one.
  const scale = Math.max(fastMs ?? 0, healMs ?? 0);
  const pct = (ms: number | null) => (ms === null || scale === 0 ? null : Math.max((ms / scale) * 100, 2));

  return (
    <section aria-labelledby="measure-title" className="mt-12">
      <h2 id="measure-title" className="text-xl">Cached run against agent repair</h2>
      <div className="mt-5 grid border-y-[1.5px] border-ink md:grid-cols-[1fr_1fr_minmax(0,0.8fr)]">
        <Measure label="Fast replay" costLabel="Cached cost" ms={fastMs} cost={benchmarks.fastCost} width={pct(fastMs)} tone="success" />
        <Measure label="Agent re-indexing" costLabel="Agent cost" ms={healMs} cost={benchmarks.healCost} width={pct(healMs)} tone="warning" />
        <div className="flex flex-col justify-center border-t-[1.5px] border-ink px-1 py-6 md:border-l-[1.5px] md:border-t-0 md:px-8">
          <span className="font-display text-hero text-ink">{ratio !== null ? `${Math.round(ratio)}×` : "n/a"}</span>
          <span className="mt-3 text-sm text-ink-muted">
            {ratio !== null ? "slower when the page has changed and the agent has to repair it" : "Run both paths to compare them"}
          </span>
        </div>
      </div>
      {sample && <p className="mt-3 text-sm italic text-ink-muted">Sample figures from fixtures. Run the workflow for measured numbers.</p>}
    </section>
  );
}

const BAR: Record<"success" | "warning", string> = { success: "bg-success", warning: "bg-warning" };

function Measure({ label, costLabel, ms, cost, width, tone }: {
  label: string; costLabel: string; ms: number | null; cost: number | null; width: number | null; tone: "success" | "warning";
}) {
  const { value, unit } = ms === null ? { value: "n/a", unit: "" } : formatMsParts(ms);
  const unknownCost = cost === null;
  return (
    <div className="px-1 py-6 md:px-8 md:first:pl-0 [&:nth-child(2)]:border-t-[1.5px] [&:nth-child(2)]:border-ink md:[&:nth-child(2)]:border-l-[1.5px] md:[&:nth-child(2)]:border-t-0">
      <div className="text-sm text-ink-muted">{label}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={`font-mono font-medium tabular-nums text-ink ${ms === null ? "text-lg italic text-ink-muted" : "text-[clamp(2.75rem,6vw,4.25rem)] leading-none"}`}>
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
      <div className="mt-5 text-sm text-ink-muted">{costLabel}</div>
      <div className={`mt-1 font-mono tabular-nums ${unknownCost ? "text-base italic text-ink-muted" : "text-xl font-medium text-ink"}`}>
        {formatUsd(cost)}
      </div>
    </div>
  );
}
