import { useEffect, useState } from "react";
import type { WorkflowSummary } from "@contracts/api_types";
import { DEFAULT_WORKFLOW, listWorkflows } from "./api/client";
import type { MockScenario } from "./api/mocks";
import { useWorkflowRun } from "./hooks/useWorkflowRun";
import { useTheme } from "./hooks/useTheme";
import { USE_MOCKS, setUseMocks } from "./config";
import Header from "./components/Header";
import ControlRow from "./components/ControlRow";
import ErrorBanner from "./components/ErrorBanner";
import BenchmarkSummary from "./components/BenchmarkSummary";
import VisualDiffViewer from "./components/VisualDiffViewer";
import RunLog from "./components/RunLog";

export default function App() {
  const [mocksOn, setMocksOn] = useState(USE_MOCKS);
  const [scenario, setScenario] = useState<MockScenario>("fast");
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([DEFAULT_WORKFLOW]);
  const [workflowId, setWorkflowId] = useState(DEFAULT_WORKFLOW.id);
  const workflow = workflows.find((w) => w.id === workflowId) ?? workflows[0];
  const { phase, result, error, benchmarks, history, trigger } = useWorkflowRun(mocksOn, workflow.id);

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

  const toggleMocks = () => {
    const next = !mocksOn;
    setUseMocks(next);
    setMocksOn(next);
  };

  const sample = mocksOn && !history.some((h) => h.workflowId === workflow.id);

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:bg-ink focus:px-4 focus:py-3 focus:text-ground">
        Skip to the run
      </a>
      <div className="mx-auto w-full max-w-[1180px] px-5 pb-24 sm:px-9">
        <Header theme={theme} onToggleTheme={toggleTheme} />

        <main id="main">
          <div className="mt-10">
            <h1 className="break-words text-[clamp(2rem,5vw,3.25rem)] leading-[1.05] tracking-tight">
              <span className="text-ink-muted">Selected:</span> <span>{workflow.id}</span>
            </h1>
            <p className="mt-2 max-w-[62ch] text-base text-ink-muted">{workflow.goal}</p>
          </div>

          <div className="mt-8">
            <ControlRow
              phase={phase}
              result={result}
              scenario={scenario}
              onScenarioChange={setScenario}
              onTrigger={() => trigger({ scenario, workflow })}
              mocksOn={mocksOn}
              onToggleMocks={toggleMocks}
              workflows={workflows}
              workflowId={workflow.id}
              onWorkflowChange={setWorkflowId}
            />
          </div>

          {phase === "error" && error && <ErrorBanner error={{ code: "request_failed", message: error.message }} />}
          {phase === "done" && result?.status === "failed" && result.error && (
            <ErrorBanner key={result.trace_id} error={result.error} cooldownRemainingS={result.cooldown_remaining_s} />
          )}

          <BenchmarkSummary benchmarks={benchmarks} sample={sample} />
          <VisualDiffViewer phase={phase} result={result} />
          <RunLog history={history} />
        </main>
      </div>
    </div>
  );
}
