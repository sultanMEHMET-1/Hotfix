const env = import.meta.env;

/**
 * Mock API switch. Set VITE_USE_MOCKS=false to call the real backend by default.
 * Live-togglable at runtime from the dashboard header via `setUseMocks` - an
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
export const RESET_PATH = "/api/v1/admin/reset";
export const WORKFLOWS_PATH = "/api/v1/workflows";

/** Sentry for the dashboard: off unless a DSN is configured (keeps tests and offline demos quiet). */
export const SENTRY_DSN: string = env.VITE_SENTRY_DSN ?? "";
const replayRate = Number(env.VITE_SENTRY_REPLAY_RATE ?? "0.1");
/** Share of ordinary sessions recorded as Session Replay; every session with an error is always recorded. */
export const SENTRY_REPLAY_RATE: number = Number.isFinite(replayRate) ? Math.min(1, Math.max(0, replayRate)) : 0.1;

export const SENTRY_ORG: string = env.VITE_SENTRY_ORG ?? "";
