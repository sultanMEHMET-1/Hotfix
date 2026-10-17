import type { WorkflowExecutionResponse } from "@contracts/api_types";

export const FAST_DELAY_MS = 300;
export const HEAL_DELAY_MS = 5000;

/** Fresh 32-char lowercase hex id, same shape as a Sentry trace id. */
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

/** Template for the deterministic fast path. trace_id is replaced per call by mockRunWorkflow. */
export const fastResponse: WorkflowExecutionResponse = {
  status: "success",
  healed: false,
  execution_time_ms: 310,
  data: { workflow_id: "permit-application", permit_status: "submitted" },
  trace_id: newTraceId(),
};

/** Template for the self-healed path. trace_id is replaced per call by mockRunWorkflow. */
export const healResponse: WorkflowExecutionResponse = {
  status: "healed",
  healed: true,
  execution_time_ms: 12400,
  data: { workflow_id: "permit-application", permit_status: "submitted", cost_usd: 0.0381 },
  trace_id: newTraceId(),
  diff: { old_selector: "#submit-btn", new_selector: 'button[data-action="submit"]' },
};

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
 * Waits FAST_DELAY_MS (or HEAL_DELAY_MS when simulateHeal) and resolves with a fresh copy
 * of the matching response carrying a new unique trace_id. Rejects with an AbortError if aborted.
 */
export async function mockRunWorkflow(
  simulateHeal: boolean,
  signal?: AbortSignal,
): Promise<WorkflowExecutionResponse> {
  await delay(simulateHeal ? HEAL_DELAY_MS : FAST_DELAY_MS, signal);
  const base = simulateHeal ? healResponse : fastResponse;
  return {
    ...base,
    data: { ...base.data },
    ...(base.diff ? { diff: { ...base.diff } } : {}),
    trace_id: newTraceId(),
  };
}
