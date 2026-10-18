export type TabId = "overview" | "run-log";

export const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "run-log", label: "Run log" },
];

export default function SectionTabs({ active, onSelect }: { active: TabId; onSelect: (id: TabId) => void }) {
  return (
    <nav aria-label="Sections" className="mt-5 flex gap-5 border-b border-line">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onSelect(tab.id)}
          aria-current={tab.id === active ? "true" : undefined}
          className={`border-b-2 pb-3 pt-1 text-sm transition-colors ${
            tab.id === active ? "border-accent font-medium text-ink" : "border-transparent text-ink-muted hover:text-ink"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
