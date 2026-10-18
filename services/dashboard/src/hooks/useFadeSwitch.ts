import { useEffect, useState } from "react";

const FADE_MS = 160;

/**
 * Crossfades between values: when `value` changes, the previously displayed value
 * fades out first, then is swapped and faded back in, instead of popping instantly.
 */
export function useFadeSwitch<T>(value: T): { display: T; visible: boolean } {
  const [display, setDisplay] = useState(value);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (value === display) {
      setVisible(true); // switched away and back mid-fade: the pending timer was cleared, so restore it
      return;
    }
    setVisible(false);
    const timer = setTimeout(() => {
      setDisplay(value);
      setVisible(true);
    }, FADE_MS);
    return () => clearTimeout(timer);
  }, [value, display]);

  return { display, visible };
}

export { FADE_MS };
