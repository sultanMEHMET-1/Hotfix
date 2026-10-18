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
    expect(screen.getByText("Idle")).toBeInTheDocument();
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

  it("switches from Mocks to Demo, hiding the scenario picker, and back", () => {
    render(<App />);
    const mocks = screen.getByRole("button", { name: "Mocks" });
    const demo = screen.getByRole("button", { name: "Demo" });
    expect(mocks).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Fast")).toBeInTheDocument();

    fireEvent.click(demo);
    expect(demo).toHaveAttribute("aria-pressed", "true");
    expect(mocks).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText("Fast")).not.toBeInTheDocument();

    fireEvent.click(mocks);
    expect(mocks).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Fast")).toBeInTheDocument();
  });
});
