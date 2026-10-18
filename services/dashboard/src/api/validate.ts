import type { WorkflowExecutionResponse } from "@contracts/api_types";

const STATUSES = new Set(["success", "healed", "failed"]);
const OUTCOMES = new Set(["committed", "rolled_back", "rejected"]);

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isFiniteNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isDiff = (v: unknown) =>
  isObject(v) && typeof v.old_selector === "string" && typeof v.new_selector === "string";
const isOptionalNumber = (v: unknown) => v === undefined || v === null || isFiniteNumber(v);

/** Light runtime shape check of the contract; throws a descriptive Error on mismatch. */
export function assertWorkflowExecutionResponse(value: unknown): asserts value is WorkflowExecutionResponse {
  if (!isObject(value)) {
    throw new Error("Invalid run-workflow response: expected a JSON object");
  }
  const v = value;
  const problems: string[] = [];
  if (typeof v.status !== "string" || !STATUSES.has(v.status)) problems.push("status");
  if (!isFiniteNumber(v.execution_time_ms)) problems.push("execution_time_ms");
  if (!isObject(v.data)) problems.push("data");
  if (typeof v.healed !== "boolean") problems.push("healed");
  if (typeof v.trace_id !== "string") problems.push("trace_id");
  if (v.diff !== undefined && v.diff !== null && !isDiff(v.diff)) problems.push("diff");
  if (v.recovery_attempted !== undefined && typeof v.recovery_attempted !== "boolean")
    problems.push("recovery_attempted");
  if (
    v.error !== undefined &&
    v.error !== null &&
    !(isObject(v.error) && typeof v.error.code === "string" && typeof v.error.message === "string")
  )
    problems.push("error");
  if (
    v.heal_records !== undefined &&
    !(
      Array.isArray(v.heal_records) &&
      v.heal_records.every(
        (r) =>
          isObject(r) &&
          typeof r.field === "string" &&
          isDiff(r.diff) &&
          isObject(r.evidence) &&
          typeof r.verification_outcome === "string" &&
          OUTCOMES.has(r.verification_outcome),
      )
    )
  )
    problems.push("heal_records");
  if (!isOptionalNumber(v.agent_cost_usd)) problems.push("agent_cost_usd");
  if (!isOptionalNumber(v.agent_duration_ms)) problems.push("agent_duration_ms");
  if (!isOptionalNumber(v.cooldown_remaining_s)) problems.push("cooldown_remaining_s");
  if (problems.length > 0) {
    throw new Error(`Invalid run-workflow response: missing or malformed field(s): ${problems.join(", ")}`);
  }
}
