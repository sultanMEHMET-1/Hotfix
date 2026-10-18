import type { WorkflowExecutionResponse } from "@contracts/api_types";
import { API_BASE, RESET_PATH, RUN_WORKFLOW_PATH, USE_MOCKS } from "../config";
import { type MockScenario, mockRunWorkflow } from "./mocks";
import { assertWorkflowExecutionResponse } from "./validate";

export { assertWorkflowExecutionResponse };

export interface RunWorkflowOptions {
  /** Mock mode only: which canned outcome to return. Ignored when calling the real backend. */
  scenario?: MockScenario;
  signal?: AbortSignal;
}

export const WORKFLOW_ID = "permit-application";

/** The backend contract is { workflow, params }. These are the demo lookup's parameters. */
export const WORKFLOW_PARAMS = { permit_id: "PERMIT-2026-0042", applicant_name: "Davis Municipal Works" };

export async function runWorkflow(opts: RunWorkflowOptions = {}): Promise<WorkflowExecutionResponse> {
  const { scenario = "fast", signal } = opts;
  if (USE_MOCKS) return mockRunWorkflow(scenario, signal);

  const url = `${API_BASE}${RUN_WORKFLOW_PATH}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ workflow: WORKFLOW_ID, params: WORKFLOW_PARAMS }),
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

/**
 * Restore the committed selectors on the backend (a rehearsal reset). The backend refuses
 * with 409 while a recovery is running, and only answers loopback callers.
 */
export async function resetDemo(): Promise<{ version: number }> {
  const res = await fetch(`${API_BASE}${RESET_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  let body: { version?: unknown; detail?: unknown } = {};
  try {
    body = await res.json();
  } catch {
    /* not JSON */
  }
  if (!res.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : `Reset failed (HTTP ${res.status})`);
  }
  if (typeof body.version !== "number") throw new Error("Reset returned an unexpected response");
  return { version: body.version };
}
