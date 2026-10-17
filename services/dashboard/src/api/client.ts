import type { WorkflowExecutionResponse } from "@contracts/api_types";
import { API_BASE, RUN_WORKFLOW_PATH, USE_MOCKS } from "../config";
import { mockRunWorkflow } from "./mocks";

export interface RunWorkflowOptions {
  /** Mock mode only: return the slow self-healed response instead of the fast path. */
  simulateHeal?: boolean;
  signal?: AbortSignal;
}

export const WORKFLOW_ID = "permit-application";

const STATUSES = new Set(["success", "healed", "failed"]);

/** Light runtime shape check of the contract; throws a descriptive Error on mismatch. */
export function assertWorkflowExecutionResponse(value: unknown): asserts value is WorkflowExecutionResponse {
  const problems: string[] = [];
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Invalid run-workflow response: expected a JSON object");
  }
  const v = value as Record<string, unknown>;
  if (typeof v.status !== "string" || !STATUSES.has(v.status)) problems.push("status");
  if (typeof v.execution_time_ms !== "number" || !Number.isFinite(v.execution_time_ms))
    problems.push("execution_time_ms");
  if (typeof v.data !== "object" || v.data === null || Array.isArray(v.data)) problems.push("data");
  if (typeof v.healed !== "boolean") problems.push("healed");
  if (typeof v.trace_id !== "string") problems.push("trace_id");
  if (v.diff !== undefined && v.diff !== null) {
    const d = v.diff as Record<string, unknown>;
    if (typeof d !== "object" || typeof d.old_selector !== "string" || typeof d.new_selector !== "string")
      problems.push("diff");
  }
  if (problems.length > 0) {
    throw new Error(`Invalid run-workflow response: missing or malformed field(s): ${problems.join(", ")}`);
  }
}

export async function runWorkflow(opts: RunWorkflowOptions = {}): Promise<WorkflowExecutionResponse> {
  const { simulateHeal = false, signal } = opts;
  if (USE_MOCKS) return mockRunWorkflow(simulateHeal, signal);

  const url = `${API_BASE}${RUN_WORKFLOW_PATH}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ workflow_id: WORKFLOW_ID }),
    signal,
  });

  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.text()).slice(0, 300);
    } catch {
      /* ignore body read errors */
    }
    throw new Error(
      `run-workflow failed: POST ${url} returned ${res.status}${res.statusText ? ` ${res.statusText}` : ""}${
        detail ? `: ${detail}` : ""
      }`,
    );
  }

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new Error(`Invalid run-workflow response: POST ${url} did not return valid JSON`);
  }
  assertWorkflowExecutionResponse(body);
  return body;
}
