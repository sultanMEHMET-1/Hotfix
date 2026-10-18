import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import App from "../App";
import CreateWorkflow from "../components/CreateWorkflow";
import { setUseMocks } from "../config";
import { deleteWorkflow, listWorkflows } from "../api/client";
import { isCreated, publicSite, workflowLabel, workflowTitle } from "../lib/workflowLabel";

const flush = () => act(async () => { await vi.advanceTimersByTimeAsync(3000); });

describe("CreateWorkflow (mock mode)", () => {
  beforeEach(() => { vi.useFakeTimers(); setUseMocks(true); });
  afterEach(() => { cleanup(); vi.useRealTimers(); });

  const setup = () => {
    const onKept = vi.fn();
    const onDeleted = vi.fn();
    render(<CreateWorkflow site="wikipedia" selectedId="wikipedia-article" onKept={onKept} onDeleted={onDeleted} />);
    return { onKept, onDeleted };
  };

  it("needs a real sentence before it can create, and shows the limits up front", () => {
    setup();
    const button = screen.getByRole("button", { name: "Create workflow" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("What should it read?"), { target: { value: "hi" } });
    expect(button).toBeDisabled();
    expect(screen.getByText(/Reads only/)).toBeInTheDocument();
    expect(screen.getByText(/Wikipedia and python.org only/)).toBeInTheDocument();
  });

  it("previews what was built in plain words, then keeps it", async () => {
    const { onKept } = setup();
    fireEvent.change(screen.getByLabelText("What should it read?"), { target: { value: "Open the article for Marie Curie and read its heading" } });
    fireEvent.click(screen.getByRole("button", { name: "Create workflow" }));
    expect(screen.getByRole("status")).toHaveTextContent("Reading the page and testing the result");
    await flush();
    expect(screen.getByText("Types {topic} into Search Wikipedia")).toBeInTheDocument();
    expect(screen.getByText("Clicks Search")).toBeInTheDocument();
    expect(screen.getByText(/"heading": "Marie Curie"/)).toBeInTheDocument();
    expect(screen.getByText(/Tested on two different inputs/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save workflow" }));
    await flush();
    expect(onKept).toHaveBeenCalledTimes(1);
    expect(onKept.mock.calls[0][0].id).toBe("custom-wikipedia-demo-0001");
    expect((await listWorkflows()).some((w) => w.id === "custom-wikipedia-demo-0001")).toBe(true);
    await deleteWorkflow("custom-wikipedia-demo-0001");  // the mock list is shared, so leave it as found
    expect((await listWorkflows()).some((w) => w.id === "custom-wikipedia-demo-0001")).toBe(false);
  });

  it("discards a preview without keeping anything", async () => {
    const { onKept } = setup();
    fireEvent.change(screen.getByLabelText("What should it read?"), { target: { value: "Open the article for Marie Curie" } });
    fireEvent.click(screen.getByRole("button", { name: "Create workflow" }));
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.queryByRole("button", { name: "Save workflow" })).toBeNull();
    expect(onKept).not.toHaveBeenCalled();
  });

  it("offers delete only for a workflow that was created, and removes it", async () => {
    const onDeleted = vi.fn();
    const { rerender } = render(<CreateWorkflow site="python" selectedId="python-latest-release" onKept={vi.fn()} onDeleted={onDeleted} />);
    expect(screen.queryByRole("button", { name: "Delete workflow" })).toBeNull();
    rerender(<CreateWorkflow site="python" selectedId="custom-python-demo-0001" onKept={vi.fn()} onDeleted={onDeleted} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete workflow" }));
    await flush();
    expect(onDeleted).toHaveBeenCalledWith("custom-python-demo-0001");
  });
});

describe("CreateWorkflow (live mode shows the backend's own words)", () => {
  beforeEach(() => { setUseMocks(false); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); setUseMocks(true); });

  it("shows the refusal message from the backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: "not_read_only", message: "Only requests that read information can be created" } }),
      { status: 422, headers: { "Content-Type": "application/json" } })));
    render(<CreateWorkflow site="wikipedia" selectedId="wikipedia-article" onKept={vi.fn()} onDeleted={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("What should it read?"), { target: { value: "edit the Alan Turing article" } });
    fireEvent.click(screen.getByRole("button", { name: "Create workflow" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only requests that read information can be created");
  });
});

describe("the page and the helpers", () => {
  afterEach(() => { cleanup(); setUseMocks(true); });

  it("offers creation only on the two public sites", async () => {
    vi.useFakeTimers();
    render(<App />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(screen.queryByText("Create a workflow from a sentence")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Wikipedia" }));
    expect(screen.getByText("Create a workflow from a sentence")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Inventory desk/ }));
    expect(screen.queryByText("Create a workflow from a sentence")).toBeNull();
    vi.useRealTimers();
  });

  it("names created workflows by their goal and maps ids to sites", () => {
    expect(workflowLabel("custom-wikipedia-x-1", "Search for a topic and read the heading.")).toBe("Search for a topic and read…");
    expect(workflowLabel("custom-wikipedia-x-1", "Read a heading.")).toBe("Read a heading");
    expect(workflowTitle("custom-wikipedia-x-1", "Search for a topic and read the heading.")).toBe("Search for a topic and read the heading");
    expect(workflowTitle("wikipedia-article", "anything")).toBe("Wikipedia");
    expect(isCreated("custom-python-x-1")).toBe(true);
    expect(isCreated("record-update")).toBe(false);
    expect([publicSite("wikipedia-article"), publicSite("custom-python-x-1"), publicSite("permit-application")]).toEqual(["wikipedia", "python", undefined]);
  });
});
