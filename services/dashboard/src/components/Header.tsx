import { m, useReducedMotion } from "framer-motion";
import type { Theme } from "../hooks/useTheme";
import Tooltip from "./Tooltip";

export interface HeaderProps {
  theme: Theme;
  onToggleTheme: () => void;
}

const ICON = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;

function Moon() {
  return <svg {...ICON} aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" /></svg>;
}

function Sun() {
  return (
    <svg {...ICON} aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

/** A frosted bar that stays at the top while the page scrolls under it. The theme swap is instant on purpose. */
export default function Header({ theme, onToggleTheme }: HeaderProps) {
  const isDark = theme === "dark";
  const reduce = useReducedMotion();
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";
  // The icon shows what a click does: a moon while the page is light, a sun while it is dark. Each flips in as the other flips out.
  const flip = (visible: boolean) => ({
    animate: { opacity: visible ? 1 : 0, rotate: reduce ? 0 : visible ? 0 : -90 },
    transition: { duration: reduce ? 0 : 0.25, ease: "easeOut" as const },
  });

  return (
    <m.header
      className="glass-bar sticky top-0 z-50"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <div className="mx-auto flex h-16 w-full max-w-[1180px] items-center justify-between gap-4 px-5 sm:px-9">
        <span className="cursor-default select-none font-display text-xl tracking-tight">Mender</span>
        <Tooltip label={isDark ? "Switch to light" : "Switch to dark"} align="end">
          <button type="button" onClick={onToggleTheme} aria-label={label} className="grid h-11 w-11 place-items-center text-ink-muted transition-colors hover:text-ink">
            <span className="relative grid h-5 w-5 place-items-center">
              <m.span aria-hidden="true" style={{ gridArea: "1 / 1" }} initial={false} {...flip(!isDark)}><Moon /></m.span>
              <m.span aria-hidden="true" style={{ gridArea: "1 / 1" }} initial={false} {...flip(isDark)}><Sun /></m.span>
            </span>
          </button>
        </Tooltip>
      </div>
    </m.header>
  );
}
