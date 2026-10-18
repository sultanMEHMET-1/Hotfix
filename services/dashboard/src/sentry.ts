import * as Sentry from "@sentry/react";
import { SENTRY_DSN, SENTRY_REPLAY_RATE } from "./config";

/** Starts Sentry in the browser only when a DSN is configured. Returns whether it started. */
export function initSentry(): boolean {
  if (!SENTRY_DSN) return false;
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    integrations: [
      Sentry.browserTracingIntegration(),
      // The dashboard shows demo data only, so keep text readable: a masked replay is useless on stage.
      Sentry.replayIntegration({ maskAllText: false, blockAllMedia: false }),
    ],
    tracesSampleRate: 1.0,
    // Same-origin /api calls (through the Vite proxy) carry the trace into the backend and the agent.
    tracePropagationTargets: [/^\/api\//, "localhost", "127.0.0.1"],
    replaysSessionSampleRate: SENTRY_REPLAY_RATE,
    replaysOnErrorSampleRate: 1.0,
  });
  return true;
}
