import type { RecoveryError } from "@contracts/api_types";

export default function ErrorBanner({ error }: { error: RecoveryError }) {
  return (
    <div className="mb-5 mt-4 flex animate-fade-up flex-col gap-0.5 rounded-xl border border-danger/20 bg-danger-bg px-4 py-3">
      <span className="font-mono text-xs text-danger">{error.code}</span>
      <span className="text-sm text-danger">{error.message}</span>
    </div>
  );
}
