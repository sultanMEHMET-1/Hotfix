import { sentryTraceUrl } from "../lib/sentry";

export default function SentryButton({ traceId }: { traceId: string | null }) {
  const url = traceId ? sentryTraceUrl(traceId) : null;

  if (!url) {
    return <span className="text-sm text-ink-muted">Sentry not configured</span>;
  }

  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex min-h-[44px] items-center text-sm text-ink underline decoration-2 underline-offset-4 hover:decoration-ink"
    >
      View Sentry trace
    </a>
  );
}
