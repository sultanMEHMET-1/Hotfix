import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import App from "../App";
import ResetButton from "../components/ResetButton";
import { HEAL_DELAY_MS, FAST_DELAY_MS } from "../api/mocks";
import { setUseMocks } from "../config";

async function run(scenario: "Fast" | "Heal" | "Rollback", ms: number) {
  fireEvent.click(screen.getByRole("button", { name: scenario }));
  fireEvent.click(screen.getByRole("button", { name: "Trigger workflow" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(ms + 50); });
}

describe("corrections pile up", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { cleanup(); vi.useRealTimers(); setUseMocks(true); });

  it("keeps earlier repairs when a later run changes nothing", async () => {
    render(<App />);
    await run("Heal", HEAL_DELAY_MS);
    expect(screen.getAllByText("Committed")).toHaveLength(2);
    await run("Fast", FAST_DELAY_MS);
    expect(screen.getAllByText("Committed")).toHaveLength(2);
    expect(screen.getByText(/The latest run used the cache and changed nothing/)).toBeInTheDocument();
    expect(screen.queryByText("No selector changes. The cache is still fresh.")).toBeNull();
  });

  it("adds each new repair and rolled-back attempt to the list, newest first", async () => {
    render(<App />);
    await run("Heal", HEAL_DELAY_MS);
    await run("Rollback", HEAL_DELAY_MS);
    expect(screen.getAllByText("Committed")).toHaveLength(2);
    expect(screen.getAllByText("Rolled back")).toHaveLength(2);
    const groups = screen.getAllByRole("group").filter((g) => g.getAttribute("aria-label")?.startsWith("Corrections from"));
    expect(groups).toHaveLength(2);
    expect(groups[0]).toHaveTextContent("failed");  // the rollback is newer
    expect(groups[1]).toHaveTextContent("healed");
  });

  it("clears on request, and a repair made after clearing shows up again", async () => {
    render(<App />);
    await run("Heal", HEAL_DELAY_MS);
    fireEvent.click(screen.getByRole("button", { name: "Clear corrections" }));
    expect(screen.queryByText("Committed")).toBeNull();
    expect(screen.queryByRole("button", { name: "Clear corrections" })).toBeNull();
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });  // a person takes longer than a millisecond to click again
    await run("Heal", HEAL_DELAY_MS);
    expect(screen.getAllByText("Committed")).toHaveLength(2);
  });

  it("lists only the selected workflow's corrections", async () => {
    render(<App />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    await run("Heal", HEAL_DELAY_MS);
    expect(screen.getAllByText("Committed")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Wikipedia" }));
    expect(screen.queryByText("Committed")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Permit portal" }));
    expect(screen.getAllByText("Committed")).toHaveLength(2);
  });
});

describe("Reset selectors", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("tells the page the repairs were undone", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ version: 4, blocked: null }), { status: 200, headers: { "Content-Type": "application/json" } })));
    const onReset = vi.fn();
    render(<ResetButton disabled={false} onReset={onReset} />);
    fireEvent.click(screen.getByRole("button", { name: "Reset selectors" }));
    await waitFor(() => expect(onReset).toHaveBeenCalledTimes(1));
  });
});
