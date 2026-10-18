import type { WorkflowExecutionResponse } from "@contracts/api_types";

type CostFields = Pick<WorkflowExecutionResponse, "healed" | "recovery_attempted" | "agent_cost_usd">;

/**
 * Whether the Browser Use agent ran for this request. Legacy responses without
 * `recovery_attempted` fall back to `healed`, per contracts/README.md.
 */
export function usedAgent(res: Pick<WorkflowExecutionResponse, "healed" | "recovery_attempted">): boolean {
  return res.recovery_attempted ?? res.healed;
}

/** Label for which execution path served the request. */
export function executionPathLabel(res: Pick<WorkflowExecutionResponse, "healed" | "recovery_attempted">): string {
  return usedAgent(res) ? "Browser Use Agent Engaged" : "Deterministic Playwright";
}

/**
 * Cost of a run in USD. A deterministic run costs 0. An agent run uses `agent_cost_usd`;
 * when the backend omits it (unavailable, or a joined request) the cost is unknown and this
 * returns null. Never treat an unknown cost as zero.
 */
export function runCostUsd(res: CostFields): number | null {
  if (!usedAgent(res)) return 0;
  const c = res.agent_cost_usd;
  return typeof c === "number" && Number.isFinite(c) ? c : null;
}
