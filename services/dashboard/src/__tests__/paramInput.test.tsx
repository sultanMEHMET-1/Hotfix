import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WorkflowSummary } from "@contracts/api_types";
import App from "../App";
import { setUseMocks } from "../config";

const wiki: WorkflowSummary = { id: "wikipedia-article", goal: "Look up an article", mutates: false, default: false,
  params_schema: {}, example_params: { title: "Alan Turing" } };
const ucla: WorkflowSummary = { id: "ucla-class-status", goal: "Read a class", mutates: false, default: false,
  params_schema: {}, example_params: { subject: "COM SCI", course_number: "35L", term: "26F" } };
const permit: WorkflowSummary = { id: "permit-application", goal: "Look up a permit", mutates: false, default: true,
  params_schema: {}, example_params: { permit_id: "P-1" } };
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
const ok = { status: "success", execution_time_ms: 300, data: { heading: "Ada Lovelace" }, healed: false, trace_id: "a".repeat(32) };

describe("typing the input of a public workflow (live mode)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(async () => {
    setUseMocks(false);
    fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(String(url).endsWith("/workflows") ? json([permit, wiki, ucla]) : json(ok)));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); setUseMocks(true); });

  const select = () => fireEvent.click(screen.getByRole("button", { name: /Wikipedia/ }));

  it("has no input on the permit portal, and one on Wikipedia that starts as the example", () => {
    expect(screen.queryByLabelText("Article title")).not.toBeInTheDocument();
    select();
    expect(screen.getByLabelText("Article title")).toHaveValue("Alan Turing");
  });

  it("runs with what was typed, and Enter runs it", async () => {
    select();
    fireEvent.change(screen.getByLabelText("Article title"), { target: { value: "  Ada Lovelace " } });
    fireEvent.submit(screen.getByRole("form", { name: "Workflow input" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/run-workflow"))!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({ workflow: "wikipedia-article", params: { title: "Ada Lovelace" } });
    expect(screen.getByRole("term")).toHaveTextContent("heading");
    expect(screen.getByRole("definition")).toHaveTextContent("Ada Lovelace");
  });

  it("types a UCLA subject, course number and term, and sends exactly those", async () => {
    fireEvent.click(screen.getByRole("button", { name: /UCLA classes/ }));
    expect(screen.getByLabelText(/^Course number/)).toHaveValue("35L");
    fireEvent.change(screen.getByLabelText(/^Course number/), { target: { value: " 32 " } });
    fireEvent.change(screen.getByLabelText(/^Subject area/), { target: { value: "MATH" } });
    fireEvent.submit(screen.getByRole("form", { name: "Workflow input" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/run-workflow"))!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      workflow: "ucla-class-status", params: { subject: "MATH", course_number: "32", term: "26F" } });
  });

  it("will not run an empty input and says why", () => {
    select();
    fireEvent.change(screen.getByLabelText("Article title"), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Trigger workflow" })).toBeDisabled();
    expect(screen.getByText("Enter a value to run.")).toBeInTheDocument();
    fireEvent.submit(screen.getByRole("form", { name: "Workflow input" }));
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/run-workflow"))).toBe(false);
  });
});
