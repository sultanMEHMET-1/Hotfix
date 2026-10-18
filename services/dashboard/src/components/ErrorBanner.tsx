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
    <div role="alert" className="mt-8 flex flex-col gap-2 rounded-panel border-[1.5px] border-danger bg-danger-bg px-6 py-5 text-danger">
      <p className="font-display text-lg leading-snug">{error.message}</p>
      <span className="font-mono text-sm">{error.code}</span>
      {left !== null && (
        <span className="text-sm" role="timer">
          {left > 0 ? `Cached failure: retry in ${Math.ceil(left)} s` : "Cooldown over: a retry will run again"}
        </span>
      )}
    </div>
  );
}
