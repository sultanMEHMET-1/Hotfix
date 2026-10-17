/**
 * Shared API types for the Mender contracts.
 *
 * Mirrors contracts/api_types.py, contracts/selectors.schema.json, and
 * contracts/failure_payload.schema.json. The dashboard consumes these
 * interfaces and must not redefine them.
 */

/** Deterministic element targeting for one workflow. */
export interface SelectorMap {
  workflow_id: string;
  target_url: string;
  version: number;
  /** Semantic field name to CSS selector. */
  fields: Record<string, string>;
}

/** Artifact emitted when deterministic execution times out or fails. */
export interface FailurePayload {
  workflow_id: string;
  /** Unix epoch milliseconds. */
  timestamp: number;
  failed_step: string;
  expected_selector: string;
  page_url: string;
  /** HTML fragment showing broken or shifted markup. */
  dom_snippet: string;
  screenshot_path: string;
  error_message: string;
}

/** Selector change applied by the healer for one semantic field. */
export interface SelectorDiff {
  old_selector: string;
  new_selector: string;
}

export type WorkflowExecutionStatus = "success" | "healed" | "failed";

/** Result returned after a workflow run, including an optional heal. */
export interface WorkflowExecutionResponse {
  status: WorkflowExecutionStatus;
  execution_time_ms: number;
  data: Record<string, unknown>;
  healed: boolean;
  trace_id: string;
  diff?: SelectorDiff;
}
