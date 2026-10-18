import { sentryTraceUrl } from "../lib/sentry";

export default function SentryButton({ traceId }: { traceId: string | null }) {
  const url = traceId ? sentryTraceUrl(traceId) : null;

  if (!url) {
    return <span className="text-xs text-ink-faint">Sentry not configured</span>;
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="text-xs text-accent underline decoration-accent/30 underline-offset-4 transition-colors hover:decoration-accent"
    >
      View Sentry trace
    </a>
  );
}
