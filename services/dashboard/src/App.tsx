import { useEffect, useState } from "react";
import type { WorkflowSummary } from "@contracts/api_types";
import { DEFAULT_WORKFLOW, listWorkflows } from "./api/client";
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
  const [mocksOn, setMocksOn] = useState(USE_MOCKS);
  const { phase, result, error, benchmarks, history, trigger } = useWorkflowRun(mocksOn);
  const [scenario, setScenario] = useState<MockScenario>("fast");
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([DEFAULT_WORKFLOW]);
  const [workflowId, setWorkflowId] = useState(DEFAULT_WORKFLOW.id);
  const workflow = workflows.find((w) => w.id === workflowId) ?? workflows[0];

  // Ask the backend what it can run (mock mode offers two canned workflows).
  useEffect(() => {
    const controller = new AbortController();
    listWorkflows(controller.signal).then(
      (list) => {
        setWorkflows(list.length ? list : [DEFAULT_WORKFLOW]);
        setWorkflowId((current) => (list.some((w) => w.id === current) ? current : (list[0] ?? DEFAULT_WORKFLOW).id));
      },
      () => setWorkflows([DEFAULT_WORKFLOW]),
    );
    return () => controller.abort();
  }, [mocksOn]);
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
        <Header workflowId={workflow.id} mocksOn={mocksOn} onToggleMocks={toggleMocks} theme={theme} onToggleTheme={toggleTheme} />

        <ControlRow
          phase={phase}
          result={result}
          scenario={scenario}
          onScenarioChange={setScenario}
          onTrigger={() => trigger({ scenario, workflow })}
          mocksOn={mocksOn}
          workflows={workflows}
          workflowId={workflow.id}
          onWorkflowChange={setWorkflowId}
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
