import type { Theme } from "../hooks/useTheme";

export interface HeaderProps {
  theme: Theme;
  onToggleTheme: () => void;
}

/** The running head of the page: the product name over a double rule, like a bound notebook. */
export default function Header({ theme, onToggleTheme }: HeaderProps) {
  const isDark = theme === "dark";
  return (
    <header className="flex items-center justify-between gap-4 border-b-4 border-double border-ink pb-3 pt-6">
      <span className="font-display text-xl tracking-tight">Mender</span>
      <button
        type="button"
        onClick={onToggleTheme}
        aria-pressed={isDark}
        title="Switch between light and dark"
        className="min-h-[44px] rounded-panel border-[1.5px] border-transparent px-3 text-sm text-ink-muted underline decoration-line decoration-2 underline-offset-4 hover:text-ink hover:decoration-ink"
      >
        {isDark ? "Use light paper" : "Use dark paper"}
      </button>
    </header>
  );
}
