import { SENTRY_ORG } from "../config";

/** Deep link to a Sentry performance trace, or null when org or traceId is empty. */
export function sentryTraceUrl(traceId: string, org: string = SENTRY_ORG): string | null {
  if (!org || !traceId) return null;
  return `https://${org}.sentry.io/explore/traces/trace/${traceId}/`;
}
