import { WORKFLOW_ID } from "../api/client";
import type { Theme } from "../hooks/useTheme";

export interface HeaderProps {
  mocksOn: boolean;
  onToggleMocks: () => void;
  theme: Theme;
  onToggleTheme: () => void;
}

export default function Header({ mocksOn, onToggleMocks, theme, onToggleTheme }: HeaderProps) {
  const isDark = theme === "dark";
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 pt-6">
      <div className="animate-fade-up">
        <div className="text-xs tracking-wide text-ink-faint">
          Mender&nbsp;&nbsp;/&nbsp;&nbsp;<span className="font-mono">{WORKFLOW_ID}</span>&nbsp;&nbsp;/
        </div>
        <h1 className="mt-1 text-xl font-semibold tracking-tight text-ink sm:text-2xl">Workflow overview</h1>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleTheme}
          aria-pressed={isDark}
          title="Switch between light and dark"
          className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
            isDark ? "border-accent bg-accent/10 text-accent" : "border-line bg-surface text-ink-muted hover:text-ink"
          }`}
        >
          {isDark ? "Dark mode" : "Light mode"}
        </button>
        <button
          type="button"
          onClick={onToggleMocks}
          aria-pressed={mocksOn}
          title="Switch between mocked demo responses and the real backend"
          className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
            mocksOn ? "border-accent bg-accent/10 text-accent" : "border-line bg-surface text-ink-muted hover:text-ink"
          }`}
        >
          Mocks {mocksOn ? "on" : "off"}
        </button>
      </div>
    </header>
  );
}
