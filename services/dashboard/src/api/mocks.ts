import type { WorkflowExecutionResponse } from "@contracts/api_types";
// Mock responses are the agreed contract fixtures, imported read-only.
import successFixture from "@contracts/fixtures/workflow_success.json";
import healedFixture from "@contracts/fixtures/workflow_healed.json";
import rolledBackFixture from "@contracts/fixtures/workflow_rolled_back.json";
import { assertWorkflowExecutionResponse } from "./validate";

/** Which canned backend outcome the mock returns. */
export type MockScenario = "fast" | "heal" | "rollback";

export const FAST_DELAY_MS = 300;
export const HEAL_DELAY_MS = 5000;

function fixture(value: unknown): WorkflowExecutionResponse {
  assertWorkflowExecutionResponse(value);
  return value;
}

/** Deterministic fast path (contracts/fixtures/workflow_success.json). */
export const fastResponse = fixture(successFixture);
/** Agent recovery that committed (contracts/fixtures/workflow_healed.json). */
export const healResponse = fixture(healedFixture);
/** Agent recovery that failed verification and was rolled back (contracts/fixtures/workflow_rolled_back.json). */
export const rollbackResponse = fixture(rolledBackFixture);

const RESPONSES: Record<MockScenario, WorkflowExecutionResponse> = {
  fast: fastResponse,
  heal: healResponse,
  rollback: rollbackResponse,
};

/** Fresh 32-char lowercase hex id, same shape as a trace id. */
export function newTraceId(): string {
  const bytes = new Uint8Array(16);
  const c = globalThis.crypto;
  if (c && typeof c.getRandomValues === "function") {
    c.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function abortError(): Error {
  return typeof DOMException !== "undefined"
    ? new DOMException("The operation was aborted.", "AbortError")
    : Object.assign(new Error("The operation was aborted."), { name: "AbortError" });
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Waits FAST_DELAY_MS for the fast path or HEAL_DELAY_MS for agent scenarios, then resolves
 * with a deep copy of the matching fixture carrying a new unique trace_id.
 * Rejects with an AbortError if aborted.
 */
export async function mockRunWorkflow(
  scenario: MockScenario,
  signal?: AbortSignal,
): Promise<WorkflowExecutionResponse> {
  await delay(scenario === "fast" ? FAST_DELAY_MS : HEAL_DELAY_MS, signal);
  return { ...structuredClone(RESPONSES[scenario]), trace_id: newTraceId() };
}
