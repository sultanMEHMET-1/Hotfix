import type { WorkflowExecutionResponse } from "@contracts/api_types";
import { API_BASE, RUN_WORKFLOW_PATH, USE_MOCKS } from "../config";
import { type MockScenario, mockRunWorkflow } from "./mocks";
import { assertWorkflowExecutionResponse } from "./validate";

export { assertWorkflowExecutionResponse };

export interface RunWorkflowOptions {
  /** Mock mode only: which canned outcome to return. Ignored when calling the real backend. */
  scenario?: MockScenario;
  signal?: AbortSignal;
}

export const WORKFLOW_ID = "permit-application";

export async function runWorkflow(opts: RunWorkflowOptions = {}): Promise<WorkflowExecutionResponse> {
  const { scenario = "fast", signal } = opts;
  if (USE_MOCKS) return mockRunWorkflow(scenario, signal);

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
