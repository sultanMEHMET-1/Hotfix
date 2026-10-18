/**
 * Shared API types for the Mender contracts.
 *
 * Mirrors contracts/api_types.py and the JSON schemas. The dashboard consumes these
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

/** Stable failure code and a human-readable explanation. */
export interface RecoveryError {
  code: string;
  message: string;
}

/** Grounding evidence. History and action indices are zero-based. */
export interface HealEvidence {
  action_type: string;
  history_step: number;
  action_index: number;
  node_name: string;
  attributes: Record<string, string>;
  reasoning: string;
  accessible_name?: string | null;
  xpath?: string | null;
}

/** Final disposition, never a claim that a provisional patch is committed. */
export interface HealRecord {
  field: string;
  diff: SelectorDiff;
  evidence: HealEvidence;
  verification_outcome: "committed" | "rolled_back" | "rejected";
  version_before: number;
  version_after?: number | null;
  rollback_version?: number | null;
}

/** Result returned after a workflow run, including an optional heal. */
export interface WorkflowExecutionResponse {
  status: WorkflowExecutionStatus;
  execution_time_ms: number;
  data: Record<string, unknown>;
  healed: boolean;
  trace_id: string;
  diff?: SelectorDiff | null;
  recovery_attempted?: boolean;
  error?: RecoveryError | null;
  heal_records?: HealRecord[];
  /** Omit when unavailable or when this request joined another recovery. */
  agent_cost_usd?: number | null;
  /** Total agent step time reported by Browser Use, in milliseconds. */
  agent_duration_ms?: number | null;
  /** Only on a failed response served from the failure cooldown: seconds until a retry starts a fresh recovery. */
  cooldown_remaining_s?: number | null;
}

/** One ordered action of a workflow. Input steps fill the named parameter. */
export interface WorkflowStep {
  field: string;
  action_type: "input" | "click";
  role?: string | null;
  label?: string | null;
  param?: string | null;
}

/** How one output value is read after the actions: the element's text, or one attribute. */
export interface WorkflowOutput {
  field: string;
  read: string;
}

/** A workflow any runner can execute (contracts/workflows/<id>.json). */
export interface WorkflowDefinition {
  goal: string;
  steps: WorkflowStep[];
  outputs?: Record<string, WorkflowOutput>;
  params_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  canary: { params: Record<string, unknown>; expected_output: Record<string, unknown>; ignore_paths?: string[] };
  mutates?: boolean;
}

/** One entry of GET /api/v1/workflows. */
export interface WorkflowSummary {
  id: string;
  goal: string;
  mutates: boolean;
  default: boolean;
  params_schema: Record<string, unknown>;
  example_params: Record<string, unknown>;
}

