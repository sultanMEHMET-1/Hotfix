const msFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** 310 -> "310ms", 12400 -> "12,400ms" (rounded, en-US grouping). */
export function formatMs(n: number): string {
  return `${msFormatter.format(Math.round(n))}ms`;
}

/** Same as formatMs, split into a value and unit for display with breathing room between them. */
export function formatMsParts(n: number): { value: string; unit: string } {
  return { value: msFormatter.format(Math.round(n)), unit: "ms" };
}

/** 0.0381 -> "$0.0381" (always 4 decimals); null -> "Unknown". */
export function formatUsd(n: number | null): string {
  return n === null ? "Unknown" : `$${n.toFixed(4)}`;
}
