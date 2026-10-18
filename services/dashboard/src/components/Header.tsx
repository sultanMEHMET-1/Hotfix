import type { Theme } from "../hooks/useTheme";

export interface HeaderProps {
  theme: Theme;
  onToggleTheme: () => void;
}

/** The running head of the page: the product name over a double rule, like a bound notebook. */
export default function Header({ theme, onToggleTheme }: HeaderProps) {
  return (
    <header className="flex items-center justify-between gap-4 border-b-4 border-double border-ink pb-3 pt-6">
      <span className="font-display text-xl tracking-tight">Mender</span>
      <div role="group" aria-label="Color theme" className="flex">
        {(["light", "dark"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => theme !== mode && onToggleTheme()}
            aria-pressed={theme === mode}
            className={`min-h-[44px] -ml-[1.5px] border-[1.5px] border-ink px-4 font-display text-sm first:ml-0 ${
              theme === mode ? "bg-ink text-ground" : "bg-surface text-ink hover:bg-surface-subtle"
            }`}
          >
            {mode === "light" ? "Light" : "Dark"}
          </button>
        ))}
      </div>
    </header>
  );
}
