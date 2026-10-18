import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import App from "../App";
import { HEAL_DELAY_MS, FAST_DELAY_MS } from "../api/mocks";
import { setUseMocks } from "../config";

describe("App", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    setUseMocks(true);
  });

  it("renders idle state with baseline benchmarks", () => {
    render(<App />);
    expect(screen.queryByText("Idle")).toBeNull();
    expect(screen.getAllByRole("status")[0]).toBeEmptyDOMElement();
    expect(screen.getByText("Trigger workflow")).toBeInTheDocument();
    expect(screen.getAllByText("No runs yet").length).toBeGreaterThan(0);
  });

  it("runs the fast path and shows a success run-log row", async () => {
    render(<App />);
    fireEvent.click(screen.getByText("Trigger workflow"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(FAST_DELAY_MS);
    });
    expect(screen.getByText("Fast path, cached selector")).toBeInTheDocument();

    expect(screen.getByText("success")).toBeInTheDocument();
  });

  it("runs the heal scenario and shows committed heal records", async () => {
    render(<App />);
    fireEvent.click(screen.getByText("Heal"));
    fireEvent.click(screen.getByText("Trigger workflow"));

    expect(screen.getAllByText(/re-indexing/i).length).toBeGreaterThan(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEAL_DELAY_MS);
    });
    expect(screen.getByText("Healed, selector patched")).toBeInTheDocument();

    expect(screen.getByText("input_permit_id")).toBeInTheDocument();
    expect(screen.getByText("submit_button")).toBeInTheDocument();
    expect(screen.getAllByText("Committed")).toHaveLength(2);
    expect(screen.getByText("#permit-id")).toBeInTheDocument();
    expect(screen.getByText("[data-testid='permit-id']")).toBeInTheDocument();
  });

  it("runs the rollback scenario and shows the error banner plus rolled-back records", async () => {
    render(<App />);
    fireEvent.click(screen.getByText("Rollback"));
    fireEvent.click(screen.getByText("Trigger workflow"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEAL_DELAY_MS);
    });
    expect(screen.getByText(/Reverted after a failed recovery/)).toBeInTheDocument();

    expect(screen.getByText("canary_mismatch")).toBeInTheDocument();
    expect(screen.getByText(/Canary output did not match/)).toBeInTheDocument();
    expect(screen.getAllByText("Rolled back")).toHaveLength(2);

    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("shows the amber healed badge and the slowdown ratio after a heal run", async () => {
    render(<App />);
    fireEvent.click(screen.getByText("Heal"));
    fireEvent.click(screen.getByText("Trigger workflow"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEAL_DELAY_MS);
    });
    expect(screen.getAllByText("healed").length).toBeGreaterThan(0);
    expect(screen.getByText("34×")).toBeInTheDocument();
  });

  it("Live is off while the scenario buttons show, on once they are hidden, and back", () => {
    render(<App />);
    const live = screen.getByRole("button", { name: "Live" });
    expect(live).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("Fast")).toBeInTheDocument();

    fireEvent.click(live);
    expect(live).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("Fast")).not.toBeInTheDocument();

    fireEvent.click(live);
    expect(live).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("Fast")).toBeInTheDocument();
  });
});
