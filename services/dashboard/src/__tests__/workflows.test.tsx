import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WorkflowSummary } from "@contracts/api_types";
import App from "../App";
import { listWorkflows, resetDemo, runWorkflow } from "../api/client";
import WorkflowPicker from "../components/WorkflowPicker";
import { setUseMocks } from "../config";
import { computeBenchmarks, EMPTY_BENCHMARKS, type RunHistoryEntry } from "../hooks/useWorkflowRun";
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
    fireEvent.click(screen.getByRole("button", { name: /record-update/ }));
    expect(onSelect).toHaveBeenCalledWith("record-update");
    rerender(<WorkflowPicker workflows={[permit, record]} selected="permit-application" onSelect={onSelect} disabled />);
    expect(screen.getByRole("button", { name: /record-update/ })).toBeDisabled();
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
    expect(screen.getByRole("button", { name: /record-update/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /record-update/ }));
    expect(screen.getAllByText("record-update").length).toBeGreaterThan(0);
  });
});

describe("benchmarks never invent a figure", () => {
  it("falls back to the placeholders it is given, and to n/a (null) in live mode", () => {
    expect(computeBenchmarks([], EMPTY_BENCHMARKS)).toEqual({ fastMs: null, healMs: null, fastCost: null, healCost: null });
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

describe("Sentry in the browser", () => {
  it("stays off without a DSN, so tests and offline demos send nothing", () => {
    expect(initSentry()).toBe(false);
  });
});
