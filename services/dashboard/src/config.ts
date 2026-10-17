const env = import.meta.env;

/** Mock API switch. Set VITE_USE_MOCKS=false to call the real backend. */
export const USE_MOCKS: boolean = env.VITE_USE_MOCKS !== "false";

/** Empty string means same-origin, which goes through the Vite dev proxy. */
export const API_BASE: string = env.VITE_API_BASE ?? "";

export const RUN_WORKFLOW_PATH = "/api/v1/run-workflow";

export const SENTRY_ORG: string = env.VITE_SENTRY_ORG ?? "";
