import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WorkflowSummary } from "@contracts/api_types";
import App from "../App";
import { listWorkflows, resetDemo, runWorkflow } from "../api/client";
import WorkflowPicker from "../components/WorkflowPicker";
import { setUseMocks } from "../config";
import { computeBenchmarks, EMPTY_BENCHMARKS, type RunHistoryEntry } from "../hooks/useWorkflowRun";
import BenchmarkSummary from "../components/BenchmarkSummary";
import HealRecordRow from "../components/HealRecordRow";
import { initSentry } from "../sentry";

const permit: WorkflowSummary = { id: "permit-application", goal: "Look up a permit", mutates: false, default: true,
  params_schema: {}, example_params: { permit_id: "P-1", applicant_name: "Ada" } };
const record: WorkflowSummary = { id: "record-update", goal: "Edit a record", mutates: true, default: false,
  params_schema: {}, example_params: { record_id: "r", value: "v" } };
const reply = (status: number, body: unknown) =>
  vi.fn().mockImplementation(() => Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));
const success = { status: "success", execution_time_ms: 300, data: {}, healed: false, trace_id: "a".repeat(32) };

describe("client: any workflow (live mode)", () => {
  beforeEach(() => setUseMocks(false));
  afterEach(() => {
    vi.unstubAllGlobals();
    setUseMocks(true);
  });

  it("lists the backend's workflows", async () => {
    const fetchMock = reply(200, [permit, record]);
    vi.stubGlobal("fetch", fetchMock);
    expect((await listWorkflows()).map((w) => w.id)).toEqual(["permit-application", "record-update"]);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/v1\/workflows$/);
  });

  it("rejects an HTTP error and an unexpected shape", async () => {
    vi.stubGlobal("fetch", reply(503, { detail: "blocked" }));
    await expect(listWorkflows()).rejects.toThrow(/HTTP 503/);
    vi.stubGlobal("fetch", reply(200, [{ nope: true }]));
    await expect(listWorkflows()).rejects.toThrow(/unexpected/);
  });

  it("runs the chosen workflow with its own example params", async () => {
    const fetchMock = reply(200, success);
    vi.stubGlobal("fetch", fetchMock);
    await runWorkflow({ workflow: record });
    expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)).toEqual({
      workflow: "record-update", params: { record_id: "r", value: "v" } });
  });

  it("resets one workflow, or all when none is named", async () => {
    const fetchMock = reply(200, { version: 4, blocked: null });
    vi.stubGlobal("fetch", fetchMock);
    await resetDemo("record-update");
    await resetDemo();
    const bodies = fetchMock.mock.calls.map((c) => JSON.parse((c[1] as RequestInit).body as string));
    expect(bodies).toEqual([{ workflow: "record-update" }, {}]);
  });
});

describe("WorkflowPicker", () => {
  afterEach(cleanup);

  it("is hidden with one workflow, and with two lets you choose and marks the writing one", () => {
    const onSelect = vi.fn();
    const { container, rerender } = render(<WorkflowPicker workflows={[permit]} selected="permit-application" onSelect={onSelect} disabled={false} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<WorkflowPicker workflows={[permit, record]} selected="permit-application" onSelect={onSelect} disabled={false} />);
    expect(screen.getByText("writes")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Inventory desk/ }));
    expect(onSelect).toHaveBeenCalledWith("record-update");
    rerender(<WorkflowPicker workflows={[permit, record]} selected="permit-application" onSelect={onSelect} disabled />);
    expect(screen.getByRole("button", { name: /Inventory desk/ })).toBeDisabled();
  });
});

describe("App with several workflows (mock mode)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    setUseMocks(true);
  });

  it("offers both workflows and shows the chosen one in the header", async () => {
    render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole("button", { name: /Inventory desk/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Inventory desk/ }));
    expect(screen.getAllByText("Inventory desk").length).toBeGreaterThan(1);
  });
});

describe("benchmarks never invent a figure", () => {
  it("falls back to the placeholders it is given, and to n/a (null) in live mode", () => {
    expect(computeBenchmarks([], EMPTY_BENCHMARKS)).toEqual({ fastMs: null, healMs: null, healCost: null });
  });
});

describe("benchmarks follow the selected workflow", () => {
  const entry = (workflowId: string, ms: number, status: "success" | "healed"): RunHistoryEntry => ({
    id: `${workflowId}-${ms}`, workflowId, startedAt: 0, costUsd: status === "healed" ? 0.01 : 0,
    response: { ...success, status, execution_time_ms: ms, healed: status === "healed" },
  });
  const history = [entry("record-update", 16000, "healed"), entry("permit-application", 300, "success")];

  it("does not compare a permit fast run with a record-update heal", () => {
    expect(computeBenchmarks(history, EMPTY_BENCHMARKS, "permit-application")).toMatchObject({ fastMs: 300, healMs: null });
    expect(computeBenchmarks(history, EMPTY_BENCHMARKS, "record-update")).toMatchObject({ fastMs: null, healMs: 16000 });
    expect(computeBenchmarks(history, EMPTY_BENCHMARKS)).toMatchObject({ fastMs: 300, healMs: 16000 });  // no filter given
  });
});

describe("the redesigned result views", () => {
  const rec = (outcome: "committed" | "rolled_back") => ({
    field: "submit_button", diff: { old_selector: "#a", new_selector: "#b" }, verification_outcome: outcome,
    version_before: 1, version_after: outcome === "committed" ? 2 : undefined, rollback_version: outcome === "rolled_back" ? 3 : undefined,
    evidence: { action_type: "click", history_step: 0, action_index: 0, node_name: "BUTTON", accessible_name: "Save record", attributes: {}, reasoning: "internal reasoning text" },
  });

  it("headlines the ratio, and says n/a before both paths have run", () => {
    const { rerender } = render(<BenchmarkSummary benchmarks={{ fastMs: 100, healMs: 3000, healCost: 0.01 }} />);
    expect(screen.getByText("30×")).toBeInTheDocument();
    expect(screen.getByText("slower with the agent")).toBeInTheDocument();
    expect(screen.queryByText(/Cached cost/)).toBeNull();
    expect(screen.getByText("3.0")).toBeInTheDocument();
    rerender(<BenchmarkSummary benchmarks={EMPTY_BENCHMARKS} />);
    expect(screen.getAllByText("n/a").length).toBeGreaterThan(1);
  });

  it("labels fixture figures as samples", () => {
    render(<BenchmarkSummary benchmarks={{ fastMs: 100, healMs: 3000, healCost: 0.01 }} sample />);
    expect(screen.getByText(/Sample figures from fixtures/)).toBeInTheDocument();
  });

  it("draws an applied correction printed and a rolled back one as not applied", () => {
    const { container } = render(<ul><HealRecordRow record={rec("committed") as never} /><HealRecordRow record={rec("rolled_back") as never} /></ul>);
    const rows = container.querySelectorAll("li");
    expect(rows[0].className).toContain("bg-surface");
    expect(rows[0].className).not.toContain("border-dashed");
    expect(rows[1].className).toContain("border-dashed");
    expect(screen.getByText(/Not applied/)).toBeInTheDocument();
    expect(screen.getAllByText("Agent clicked Save record (button).", { exact: false }).length).toBe(2);
    expect(container.querySelector("details")).toBeNull();
  });
});

describe("Sentry in the browser", () => {
  it("stays off without a DSN, so tests and offline demos send nothing", () => {
    expect(initSentry()).toBe(false);
  });
});
