import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { FAST_DELAY_MS, HEAL_DELAY_MS } from "../api/mocks";
import { setUseMocks } from "../config";
import HealRecordRow from "../components/HealRecordRow";
import ResetButton from "../components/ResetButton";

describe("a request error is visible", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setUseMocks(false);
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    setUseMocks(true);
  });

  it("shows the backend's message and a failed badge instead of Idle", async () => {
    const detail = "Rollback failed; restore the backup and restart the backend";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 503 })));
    render(<App />);
    fireEvent.click(screen.getByText("Trigger workflow"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByText(/Rollback failed; restore the backup/)).toBeInTheDocument();
    expect(screen.getByText("Request failed")).toBeInTheDocument();
    expect(screen.queryByText("Idle")).toBeNull();
  });
});

describe("the previous result does not describe the next run", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    setUseMocks(true);
  });

  it("hides the old error banner and agent label while a new run is in flight", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Rollback" }));
    fireEvent.click(screen.getByText("Trigger workflow"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEAL_DELAY_MS);
    });
    expect(screen.getByText("Browser Use Agent Engaged")).toBeInTheDocument();
    expect(screen.getAllByText(/canary/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Fast" }));
    fireEvent.click(screen.getByText("Trigger workflow"));
    expect(screen.queryByText("Browser Use Agent Engaged")).toBeNull();
    expect(screen.queryAllByText(/canary/i)).toHaveLength(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(FAST_DELAY_MS);
    });
    expect(screen.getByText("Deterministic Playwright")).toBeInTheDocument();
  });
});

describe("HealRecordRow version labels", () => {
  afterEach(cleanup);
  const base = {
    field: "submit_button",
    diff: { old_selector: "#a", new_selector: "#b" },
    evidence: { action_type: "click", history_step: 0, action_index: 0, node_name: "BUTTON", attributes: {}, reasoning: "r" },
    version_before: 2,
  } as const;

  it("only says restored for a rolled back record", () => {
    const { rerender } = render(<HealRecordRow record={{ ...base, verification_outcome: "rejected" }} />);
    expect(screen.getByText("v2, never installed")).toBeInTheDocument();
    expect(screen.queryByText(/restored/)).toBeNull();
    rerender(<HealRecordRow record={{ ...base, verification_outcome: "rolled_back", version_after: 3, rollback_version: 4 }} />);
    expect(screen.getByText("v2, restored to v4")).toBeInTheDocument();
    rerender(<HealRecordRow record={{ ...base, verification_outcome: "committed", version_after: 3 }} />);
    expect(screen.getByText("v2 → v3")).toBeInTheDocument();
  });
});

describe("ResetButton when the backend stays blocked", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("does not report plain success", async () => {
    const body = { version: 4, blocked: "Rollback failed; restore the backup and restart the backend" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 })));
    render(<ResetButton disabled={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Reset selectors" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("backend is blocked"));
    expect(screen.getByRole("status")).not.toHaveTextContent("Selectors reset");
  });
});
