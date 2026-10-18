import type { Benchmarks } from "../hooks/useWorkflowRun";
import { formatMsParts, formatUsd } from "../lib/format";
import Reveal from "./Reveal";

export default function BenchmarkSummary({ benchmarks }: { benchmarks: Benchmarks }) {
  const ratio =
    benchmarks.fastMs !== null && benchmarks.healMs !== null && benchmarks.fastMs > 0 ? benchmarks.healMs / benchmarks.fastMs : null;

  return (
    <Reveal>
      <div className="rounded-xl border border-line bg-surface p-5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-ink-muted">Execution time</span>
          {ratio !== null && <span className="text-xs text-ink-faint">{`~${Math.round(ratio)}× slower`}</span>}
        </div>
        <div className="mt-4 flex flex-wrap gap-x-8 gap-y-5">
          <Stat label="Fast replay" ms={benchmarks.fastMs} tone="success" />
          <Stat label="Agent re-indexing" ms={benchmarks.healMs} tone="warning" />
          <CostStat label="Cached cost" value={benchmarks.fastCost} tone="success" />
          <CostStat label="Agent cost" value={benchmarks.healCost} tone="warning" />
        </div>
      </div>
    </Reveal>
  );
}

const TONE_DOT: Record<"success" | "warning", string> = { success: "bg-success", warning: "bg-warning" };

function Stat({ label, ms, tone }: { label: string; ms: number | null; tone: "success" | "warning" }) {
  const { value, unit } = ms === null ? { value: "n/a", unit: "" } : formatMsParts(ms);
  return (
    <div>
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-2xl font-semibold tabular-nums text-ink">{value}</span>
        <span className="text-sm text-ink-faint">{unit}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-faint">
        <span className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[tone]}`} />
        {label}
      </div>
    </div>
  );
}

function CostStat({ label, value, tone }: { label: string; value: number | null; tone: "success" | "warning" }) {
  const text = formatUsd(value);
  const isUnknown = value === null;
  return (
    <div>
      <span className={`font-mono tabular-nums ${isUnknown ? "text-base italic text-ink-faint" : "text-2xl font-semibold text-ink"}`}>
        {text}
      </span>
      <div className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-faint">
        <span className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[tone]}`} />
        {label}
      </div>
    </div>
  );
}
