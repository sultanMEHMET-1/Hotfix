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

/** 125 -> {125, ms}, 4200 -> {4.2, s}, 72000 -> {1 m 12, s}. Seconds take over at one second, minutes at a minute. */
export function formatDurationParts(n: number): { value: string; unit: string } {
  if (Math.round(n) < 1000) return { value: msFormatter.format(Math.round(n)), unit: "ms" };
  if (Math.round(n / 100) < 600) return { value: (n / 1000).toFixed(1), unit: "s" };
  const seconds = Math.round(n / 1000);
  return { value: `${Math.floor(seconds / 60)} m ${seconds % 60}`, unit: "s" };
}

export function formatDuration(n: number): string {
  const { value, unit } = formatDurationParts(n);
  return `${value} ${unit}`;
}
