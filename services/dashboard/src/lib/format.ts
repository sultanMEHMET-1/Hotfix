const msFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** 310 -> "310ms", 12400 -> "12,400ms" (rounded, en-US grouping). */
export function formatMs(n: number): string {
  return `${msFormatter.format(Math.round(n))}ms`;
}

/** 0.0381 -> "$0.0381" (always 4 decimals). */
export function formatUsd(n: number): string {
  return `$${n.toFixed(4)}`;
}
