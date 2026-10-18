import { useEffect, useState } from "react";

/** Milliseconds since `active` last became true; 0 while inactive. Drives the live agent clock. */
export function useElapsed(active: boolean): number {
  const [ms, setMs] = useState(0);
  useEffect(() => {
    if (!active) {
      setMs(0);
      return;
    }
    const started = performance.now();
    setMs(0);
    const timer = setInterval(() => setMs(performance.now() - started), 100);
    return () => clearInterval(timer);
  }, [active]);
  return ms;
}
