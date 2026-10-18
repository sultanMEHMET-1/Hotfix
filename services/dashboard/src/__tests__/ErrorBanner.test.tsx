import { act, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBanner from "../components/ErrorBanner";

const error = { code: "canary_failed", message: "Canary rejected provisional selectors" };

describe("ErrorBanner cooldown", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("shows no countdown for an ordinary failure", () => {
    render(<ErrorBanner error={error} />);
    expect(screen.queryByRole("timer")).toBeNull();
  });

  it("counts down from the reported seconds and then says a retry will run", () => {
    render(<ErrorBanner error={error} cooldownRemainingS={11.2} />);
    expect(screen.getByRole("timer")).toHaveTextContent("retry in 12 s");
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByRole("timer")).toHaveTextContent("retry in 9 s");
    act(() => vi.advanceTimersByTime(9000));
    expect(screen.getByRole("timer")).toHaveTextContent("Cooldown over");
  });
});
