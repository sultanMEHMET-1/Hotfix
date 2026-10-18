import type { WorkflowExecutionResponse, WorkflowSummary } from "@contracts/api_types";
import { API_BASE, RESET_PATH, RUN_WORKFLOW_PATH, USE_MOCKS, WORKFLOWS_PATH } from "../config";
import { type MockScenario, mockRunWorkflow } from "./mocks";
import { assertWorkflowExecutionResponse } from "./validate";

export { assertWorkflowExecutionResponse };

export interface RunWorkflowOptions {
  /** Mock mode only: which canned outcome to return. Ignored when calling the real backend. */
  scenario?: MockScenario;
  /** Which workflow to run, with the params to send. Defaults to the permit demo. */
  workflow?: Pick<WorkflowSummary, "id" | "example_params">;
  signal?: AbortSignal;
}

export const WORKFLOW_ID = "permit-application";

/** The backend contract is { workflow, params }. These are the demo lookup's parameters. */
export const WORKFLOW_PARAMS = { permit_id: "PERMIT-2026-0042", applicant_name: "Davis Municipal Works" };

/** Used in mock mode and when the backend's workflow list cannot be loaded. */
export const DEFAULT_WORKFLOW: WorkflowSummary = {
  id: WORKFLOW_ID,
  goal: "Look up a permit and report its status.",
  mutates: false,
  default: true,
  params_schema: {},
  example_params: WORKFLOW_PARAMS,
};

const MOCK_WORKFLOWS: WorkflowSummary[] = [
  DEFAULT_WORKFLOW,
  { id: "record-update", goal: "Edit a record and report the saved value.", mutates: true, default: false, params_schema: {},
    example_params: { record_id: "canary-record", value: "canary-value" } },
  { id: "wikipedia-article", goal: "Search Wikipedia for an article title and report its heading.", mutates: false, default: false,
    params_schema: {}, example_params: { title: "Alan Turing" } },
  { id: "python-latest-release", goal: "Open the python.org downloads page and report the newest Python release.", mutates: false,
    default: false, params_schema: {}, example_params: {} },
];

/** The workflows the backend can run (default first). Mock mode returns two canned ones. */
export async function listWorkflows(signal?: AbortSignal): Promise<WorkflowSummary[]> {
  if (USE_MOCKS) return MOCK_WORKFLOWS;
  const res = await fetch(`${API_BASE}${WORKFLOWS_PATH}`, { headers: { Accept: "application/json" }, signal });
  if (!res.ok) throw new Error(`Could not load workflows (HTTP ${res.status})`);
  const body: unknown = await res.json();
  if (!Array.isArray(body) || body.some((w) => typeof w?.id !== "string" || typeof w?.example_params !== "object")) {
    throw new Error("Could not load workflows: unexpected response");
  }
  return body as WorkflowSummary[];
}

export async function runWorkflow(opts: RunWorkflowOptions = {}): Promise<WorkflowExecutionResponse> {
  const { scenario = "fast", signal, workflow = DEFAULT_WORKFLOW } = opts;
  if (USE_MOCKS) return mockRunWorkflow(scenario, signal);

  const url = `${API_BASE}${RUN_WORKFLOW_PATH}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ workflow: workflow.id, params: workflow.example_params }),
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
export async function resetDemo(workflow?: string): Promise<{ version: number; blocked: string | null }> {
  const res = await fetch(`${API_BASE}${RESET_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow ? { workflow } : {}),
  });
  let body: { version?: unknown; detail?: unknown; blocked?: unknown } = {};
  try {
    body = await res.json();
  } catch {
    /* not JSON */
  }
  if (!res.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : `Reset failed (HTTP ${res.status})`);
  }
  if (typeof body.version !== "number") throw new Error("Reset returned an unexpected response");
  return { version: body.version, blocked: typeof body.blocked === "string" ? body.blocked : null };
}

/** What the backend built from a sentence, to preview before keeping it. */
export interface DraftPreview {
  id: string;
  workflow_id: string;
  site: "wikipedia" | "python";
  request: string;
  goal: string;
  steps: { action: "input" | "click"; label: string | null; param: string | null }[];
  params: { name: string; example: string }[];
  outputs: { name: string; description: string }[];
  sample_output: Record<string, string>;
  cost_usd: number | null;
  duration_ms: number;
  warnings: string[];
}

/** The backend's own words for a refusal (`detail.message`), so the page can show them as they are. */
async function failureMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail?.message === "string") return detail.message;
  } catch {
    /* not JSON */
  }
  return `${fallback} (HTTP ${res.status})`;
}

const MOCK_DRAFT_MS = 2500;

function mockDraft(site: DraftPreview["site"], request: string): DraftPreview {
  const wiki = site === "wikipedia";
  return {
    id: "mock-draft", workflow_id: `custom-${site}-demo-0001`, site, request,
    goal: wiki ? "Search Wikipedia for a topic and read the article heading." : "Search python.org and read the first result title.",
    steps: [
      { action: "input", label: wiki ? "Search Wikipedia" : "Search This Site", param: wiki ? "topic" : "query" },
      { action: "click", label: wiki ? "Search" : "GO", param: null },
    ],
    params: [{ name: wiki ? "topic" : "query", example: wiki ? "Marie Curie" : "decorators" }],
    outputs: [{ name: wiki ? "heading" : "first_result_title", description: wiki ? "the article heading" : "the first result title" }],
    sample_output: wiki ? { heading: "Marie Curie" } : { first_result_title: "Highlights: Python 2.4" },
    cost_usd: 0.0083, duration_ms: 16400, warnings: [],
  };
}

export async function createDraft(site: DraftPreview["site"], request: string, signal?: AbortSignal): Promise<DraftPreview> {
  if (USE_MOCKS) {
    await new Promise((resolve) => setTimeout(resolve, MOCK_DRAFT_MS));
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return mockDraft(site, request);
  }
  const res = await fetch(`${API_BASE}${WORKFLOWS_PATH}/draft`, {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ site, request }), signal,
  });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not create the workflow"));
  return (await res.json()) as DraftPreview;
}

export async function keepDraft(draft: DraftPreview): Promise<WorkflowSummary> {
  if (USE_MOCKS) {
    const summary: WorkflowSummary = { id: draft.workflow_id, goal: draft.goal, mutates: false, default: false, params_schema: {},
      example_params: Object.fromEntries(draft.params.map((p) => [p.name, p.example])) };
    MOCK_WORKFLOWS.push(summary);
    return summary;
  }
  const res = await fetch(`${API_BASE}${WORKFLOWS_PATH}/draft/${encodeURIComponent(draft.id)}/accept`, {
    method: "POST", headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not save the workflow"));
  return (await res.json()) as WorkflowSummary;
}

export async function deleteWorkflow(id: string): Promise<void> {
  if (USE_MOCKS) {
    const index = MOCK_WORKFLOWS.findIndex((w) => w.id === id);
    if (index >= 0) MOCK_WORKFLOWS.splice(index, 1);
    return;
  }
  const res = await fetch(`${API_BASE}${WORKFLOWS_PATH}/${encodeURIComponent(id)}`, { method: "DELETE", headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not delete the workflow"));
}
