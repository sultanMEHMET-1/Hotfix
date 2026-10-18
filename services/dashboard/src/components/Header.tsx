import { m } from "framer-motion";
import type { Theme } from "../hooks/useTheme";

export interface HeaderProps {
  theme: Theme;
  onToggleTheme: () => void;
}

/** A frosted bar that stays at the top while the page scrolls under it. The theme swap is instant on purpose. */
export default function Header({ theme, onToggleTheme }: HeaderProps) {
  return (
    <m.header
      className="glass-bar sticky top-0 z-50"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <div className="mx-auto flex h-16 w-full max-w-[1180px] items-center justify-between gap-4 px-5 sm:px-9">
        <span className="font-display text-xl tracking-tight">Mender</span>
        <div role="group" aria-label="Color theme" className="flex">
          {(["light", "dark"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => theme !== mode && onToggleTheme()}
              aria-pressed={theme === mode}
              className="glass-rect -ml-px min-h-[44px] px-4 font-display text-sm first:ml-0"
            >
              {mode === "light" ? "Light" : "Dark"}
            </button>
          ))}
        </div>
      </div>
    </m.header>
  );
}
