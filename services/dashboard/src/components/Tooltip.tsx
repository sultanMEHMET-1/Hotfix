import { cloneElement, useId, useRef, useState, type ReactElement } from "react";
import { AnimatePresence, m, useReducedMotion } from "framer-motion";

/**
 * A short hint for a control. Shows on hover (after a beat, so it never flashes on a pass-through) and on
 * keyboard focus, and links to its trigger with aria-describedby. Keep labels to a few words.
 */
export default function Tooltip({ label, children, align = "center", className = "" }: {
  label: string;
  children: ReactElement;
  align?: "center" | "start";
  /** Extra classes for the wrapper, for example to join a button group. */
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const reduce = useReducedMotion();
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const autoHide = useRef<ReturnType<typeof setTimeout>>();

  const show = (delay: number) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(true), delay);
  };
  const hide = () => {
    clearTimeout(timer.current);
    clearTimeout(autoHide.current);
    setOpen(false);
  };
  // Touch has no hover or blur, so a tap opens it and it closes itself after a beat.
  const tap = () => {
    clearTimeout(timer.current);
    setOpen(true);
    clearTimeout(autoHide.current);
    autoHide.current = setTimeout(() => setOpen(false), 1500);
  };

  const trigger = open ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, { "aria-describedby": id }) : children;

  return (
    <span
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => show(500)}
      onMouseLeave={hide}
      onFocusCapture={() => show(0)}
      onBlurCapture={hide}
      onClick={tap}
    >
      {trigger}
      <AnimatePresence>
        {open && (
          <m.span
            role="tooltip"
            id={id}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            className={`pointer-events-none absolute top-full z-[60] mt-2 whitespace-nowrap rounded-panel border-[1.5px] border-ink bg-surface px-2.5 py-1.5 text-sm font-medium text-ink shadow-print-sm ${
              align === "start" ? "left-0" : "left-1/2 -translate-x-1/2"
            }`}
          >
            {label}
          </m.span>
        )}
      </AnimatePresence>
    </span>
  );
}
