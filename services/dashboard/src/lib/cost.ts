import type { WorkflowExecutionResponse } from "@contracts/api_types";

/** Default cost of one agent (healing) run in USD. */
export const AGENT_RUN_COST_USD = 0.0381;

/** Cost of a run: 0 for success; data.cost_usd when finite; else AGENT_RUN_COST_USD (healed) / 0 (failed). */
export function runCostUsd(res: Pick<WorkflowExecutionResponse, "status" | "data">): number {
  if (res.status === "success") return 0;
  const c = res.data?.cost_usd;
  if (typeof c === "number" && Number.isFinite(c)) return c;
  return res.status === "healed" ? AGENT_RUN_COST_USD : 0;
}
