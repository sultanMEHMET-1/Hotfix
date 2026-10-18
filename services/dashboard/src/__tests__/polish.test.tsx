import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import App from "../App";
import Tooltip from "../components/Tooltip";
import { setUseMocks } from "../config";

describe("Tooltip", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { cleanup(); vi.useRealTimers(); });

  it("waits half a second on hover, shows at once on focus, and links to its trigger", () => {
    render(<Tooltip label="Restore original selectors"><button type="button">Reset</button></Tooltip>);
    const button = screen.getByRole("button", { name: "Reset" });
    fireEvent.mouseEnter(button.parentElement!);
    act(() => { vi.advanceTimersByTime(499); });
    expect(screen.queryByRole("tooltip")).toBeNull();
    act(() => { vi.advanceTimersByTime(2); });
    expect(screen.getByRole("tooltip")).toHaveTextContent("Restore original selectors");
    expect(button).toHaveAttribute("aria-describedby", screen.getByRole("tooltip").id);
    fireEvent.mouseLeave(button.parentElement!);
    cleanup();
    render(<Tooltip label="Cached run"><button type="button">Fast</button></Tooltip>);
    fireEvent.focus(screen.getByRole("button", { name: "Fast" }));
    act(() => { vi.advanceTimersByTime(1); });
    expect(screen.getByRole("tooltip")).toHaveTextContent("Cached run");
  });
});

describe("the page chrome", () => {
  afterEach(() => { cleanup(); setUseMocks(true); });

  it("keeps the header stuck to the top and uses no native title tooltips", () => {
    const { container } = render(<App />);
    const header = container.querySelector("header")!;
    expect(header.className).toContain("sticky");
    expect(header.className).toContain("top-0");
    expect(container.querySelectorAll("[title]")).toHaveLength(0);
  });

  it("offers the Light | Dark switch as two buttons", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "Light" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dark" })).toBeInTheDocument();
  });
});
