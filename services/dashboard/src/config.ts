const env = import.meta.env;

/**
 * Mock API switch. Set VITE_USE_MOCKS=false to call the real backend by default.
 * Live-togglable at runtime from the dashboard header via `setUseMocks` — an
 * ES module named export is a live binding, so every importer (including
 * `runWorkflow`) sees the toggled value on its next read, no plumbing needed.
 */
export let USE_MOCKS: boolean = env.VITE_USE_MOCKS !== "false";

export function setUseMocks(value: boolean): void {
  USE_MOCKS = value;
}

/** Empty string means same-origin, which goes through the Vite dev proxy. */
export const API_BASE: string = env.VITE_API_BASE ?? "";

export const RUN_WORKFLOW_PATH = "/api/v1/run-workflow";

export const SENTRY_ORG: string = env.VITE_SENTRY_ORG ?? "";
