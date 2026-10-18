import { useEffect, useState } from "react";
import type { RecoveryError } from "@contracts/api_types";

export interface ErrorBannerProps {
  error: RecoveryError;
  /** Seconds until a retry would start a fresh recovery; set only for a cached failure. */
  cooldownRemainingS?: number | null;
}

/** Counts down from the value the backend reported when the response arrived. */
function useCountdown(seconds: number | null | undefined): number | null {
  const [left, setLeft] = useState<number | null>(typeof seconds === "number" ? seconds : null);
  useEffect(() => {
    if (typeof seconds !== "number") return;
    const deadline = Date.now() + seconds * 1000;
    setLeft(seconds);
    const timer = setInterval(() => {
      const remaining = Math.max(0, (deadline - Date.now()) / 1000);
      setLeft(remaining);
      if (remaining === 0) clearInterval(timer);
    }, 250);
    return () => clearInterval(timer);
  }, [seconds]);
  return typeof seconds === "number" ? left : null;
}

export default function ErrorBanner({ error, cooldownRemainingS }: ErrorBannerProps) {
  const left = useCountdown(cooldownRemainingS);
  return (
    <div className="mb-5 mt-4 flex animate-fade-up flex-col gap-0.5 rounded-xl border border-danger/20 bg-danger-bg px-4 py-3">
      <span className="font-mono text-xs text-danger">{error.code}</span>
      <span className="text-sm text-danger">{error.message}</span>
      {left !== null && (
        <span className="text-xs text-danger" role="timer">
          {left > 0 ? `Cached failure: retry in ${Math.ceil(left)} s` : "Cooldown over: a retry will run again"}
        </span>
      )}
    </div>
  );
}
