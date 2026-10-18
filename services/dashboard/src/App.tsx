import { useEffect, useState } from "react";
import { LazyMotion, domAnimation } from "framer-motion";
import type { WorkflowSummary } from "@contracts/api_types";
import { DEFAULT_WORKFLOW, deleteWorkflow, listWorkflows } from "./api/client";
import type { MockScenario } from "./api/mocks";
import { useWorkflowRun } from "./hooks/useWorkflowRun";
import { useTheme } from "./hooks/useTheme";
import { isCreated, paramLabel, publicSite, workflowTitle, type PublicSite } from "./lib/workflowLabel";
import { USE_MOCKS, setUseMocks } from "./config";
import Header from "./components/Header";
import ControlRow from "./components/ControlRow";
import ErrorBanner from "./components/ErrorBanner";
import BenchmarkSummary from "./components/BenchmarkSummary";
import VisualDiffViewer from "./components/VisualDiffViewer";
import RunLog from "./components/RunLog";
import BlurFade from "./components/BlurFade";
import ScrollReveal from "./components/ScrollReveal";
import CreateWorkflow from "./components/CreateWorkflow";

export default function App() {
  const [mocksOn, setMocksOn] = useState(USE_MOCKS);
  const [scenario, setScenario] = useState<MockScenario>("fast");
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([DEFAULT_WORKFLOW]);
  const [workflowId, setWorkflowId] = useState(DEFAULT_WORKFLOW.id);
  // Per workflow: corrections from runs before this time are hidden (cleared by hand, or undone by a selector reset).
  const [clearedAt, setClearedAt] = useState<Record<string, number>>({});
  // Per workflow: values typed into its input boxes (public read-only workflows only).
  const [typed, setTyped] = useState<Record<string, Record<string, string>>>({});
  // "create" shows only the create-from-a-sentence flow, so nothing runnable is on screen while a draft is being made.
  const [mode, setMode] = useState<"run" | "create">("run");
  const [createSite, setCreateSite] = useState<PublicSite>("wikipedia");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const workflow = workflows.find((w) => w.id === workflowId) ?? workflows[0];
  const creating = mode === "create";
  const inputs = mocksOn || workflow.mutates || !publicSite(workflow.id) ? [] : Object.entries(workflow.example_params)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string")
    .map(([name, example]) => ({ name, label: paramLabel(workflow.id, name), example, value: typed[workflow.id]?.[name] ?? example }));
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

  const selectWorkflow = (id: string) => { setMode("run"); setDeleteError(null); setWorkflowId(id); };
  const openCreate = () => { setCreateSite(publicSite(workflow.id) ?? createSite); setMode("create"); };
  const removeCreated = async () => {
    setDeleteError(null);
    try {
      await deleteWorkflow(workflow.id);
      setWorkflows((list) => list.filter((w) => w.id !== workflow.id));
      setWorkflowId(DEFAULT_WORKFLOW.id);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    }
  };

  const toggleMocks = () => {
    const next = !mocksOn;
    setUseMocks(next);
    setMocksOn(next);
  };

  const sample = mocksOn && !history.some((h) => h.workflowId === workflow.id);

  return (
    <LazyMotion features={domAnimation}>
      <div className="min-h-screen">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[70] focus:bg-ink focus:px-4 focus:py-3 focus:text-ground">
          Skip to the run
        </a>
        <Header theme={theme} onToggleTheme={toggleTheme} />

        <div className="mx-auto w-full max-w-[1180px] px-5 pb-24 sm:px-9">
          <main id="main">
            <BlurFade className="mt-10">
              <h1 className="break-words text-[clamp(2rem,5vw,3.25rem)] leading-[1.05] tracking-tight">
                <span className="text-ink-muted">Selected:</span> <span>{creating ? "New workflow" : workflowTitle(workflow.id, workflow.goal)}</span>
              </h1>
              {!creating && !isCreated(workflow.id) && <p className="mt-2 max-w-[62ch] text-base text-ink-muted">{workflow.goal}</p>}
            </BlurFade>

            <BlurFade className="mt-8" delay={0.08}>
              <ControlRow
                phase={phase}
                result={result}
                scenario={scenario}
                onScenarioChange={setScenario}
                onTrigger={() => trigger({ scenario, workflow: { ...workflow, example_params: { ...workflow.example_params, ...Object.fromEntries(inputs.map((i) => [i.name, i.value.trim()])) } } })}
                inputs={inputs}
                onInputChange={(name, value) => setTyped((all) => ({ ...all, [workflow.id]: { ...all[workflow.id], [name]: value } }))}
                mocksOn={mocksOn}
                onToggleMocks={toggleMocks}
                workflows={workflows}
                workflowId={workflow.id}
                onWorkflowChange={selectWorkflow}
                creating={creating}
                onNew={openCreate}
                onDelete={isCreated(workflow.id) ? removeCreated : undefined}
                onReset={() => setClearedAt((c) => ({ ...c, [workflow.id]: Date.now() }))}
              />
            </BlurFade>

            {creating && (
              <ScrollReveal>
                <CreateWorkflow
                  key={createSite}
                  site={createSite}
                  onSiteChange={setCreateSite}
                  onKept={(created) => { setWorkflows((list) => [...list, created]); selectWorkflow(created.id); }}
                />
              </ScrollReveal>
            )}

            {deleteError && !creating && <ErrorBanner error={{ code: "delete_failed", message: deleteError }} />}
            {!creating && phase === "error" && error && <ErrorBanner error={{ code: "request_failed", message: error.message }} />}
            {!creating && phase === "done" && result?.status === "failed" && result.error && (
              <ErrorBanner key={result.trace_id} error={result.error} cooldownRemainingS={result.cooldown_remaining_s} />
            )}

            {!creating && (
              <>
                <ScrollReveal><BenchmarkSummary benchmarks={benchmarks} sample={sample} workflowId={workflow.id} /></ScrollReveal>
                <ScrollReveal>
                  <VisualDiffViewer
                    phase={phase} result={result} history={history} workflowId={workflow.id}
                    since={clearedAt[workflow.id] ?? 0}
                    onClear={() => setClearedAt((c) => ({ ...c, [workflow.id]: Date.now() }))}
                  />
                </ScrollReveal>
                <ScrollReveal><RunLog history={history} /></ScrollReveal>
              </>
            )}
          </main>
        </div>
      </div>
    </LazyMotion>
  );
}
