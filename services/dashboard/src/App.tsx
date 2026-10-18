import { useState } from "react";
import type { MockScenario } from "./api/mocks";
import { useWorkflowRun } from "./hooks/useWorkflowRun";
import { useTheme } from "./hooks/useTheme";
import { useFadeSwitch, FADE_MS } from "./hooks/useFadeSwitch";
import { USE_MOCKS, setUseMocks } from "./config";
import SectionTabs, { type TabId } from "./components/SectionTabs";
import Header from "./components/Header";
import ControlRow from "./components/ControlRow";
import ErrorBanner from "./components/ErrorBanner";
import BenchmarkSummary from "./components/BenchmarkSummary";
import VisualDiffViewer from "./components/VisualDiffViewer";
import RunLog from "./components/RunLog";

export default function App() {
  const { phase, result, error, benchmarks, history, trigger } = useWorkflowRun();
  const [scenario, setScenario] = useState<MockScenario>("fast");
  const [mocksOn, setMocksOn] = useState(USE_MOCKS);
  const [theme, toggleTheme] = useTheme();
  const [tab, setTab] = useState<TabId>("overview");
  const { display: displayedTab, visible: tabVisible } = useFadeSwitch(tab);

  const toggleMocks = () => {
    const next = !mocksOn;
    setUseMocks(next);
    setMocksOn(next);
  };

  return (
    <div className="min-h-screen bg-surface-subtle">
      <div className="mx-auto w-full max-w-[1120px] px-6 pb-16 sm:px-9">
        <Header mocksOn={mocksOn} onToggleMocks={toggleMocks} theme={theme} onToggleTheme={toggleTheme} />

        <ControlRow
          phase={phase}
          result={result}
          scenario={scenario}
          onScenarioChange={setScenario}
          onTrigger={() => trigger({ scenario })}
          mocksOn={mocksOn}
        />

        {phase === "error" && error && <ErrorBanner error={{ code: "request_failed", message: error.message }} />}
        {phase === "done" && result?.status === "failed" && result.error && (
          <ErrorBanner key={result.trace_id} error={result.error} cooldownRemainingS={result.cooldown_remaining_s} />
        )}

        <div className="mt-4">
          <BenchmarkSummary benchmarks={benchmarks} />
        </div>

        <SectionTabs active={tab} onSelect={setTab} />

        <div
          className="mt-4 transition-opacity ease-out"
          style={{ transitionDuration: `${FADE_MS}ms`, opacity: tabVisible ? 1 : 0 }}
        >
          {displayedTab === "overview" ? <VisualDiffViewer phase={phase} result={result} /> : <RunLog history={history} />}
        </div>
      </div>
    </div>
  );
}
