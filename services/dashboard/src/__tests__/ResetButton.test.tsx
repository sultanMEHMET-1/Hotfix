import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import ResetButton from "../components/ResetButton";

const reply = (status: number, body: unknown) =>
  vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

describe("ResetButton", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("posts to the backend reset endpoint and shows the new selector version", async () => {
    const fetchMock = reply(200, { version: 4, blocked: null });
    vi.stubGlobal("fetch", fetchMock);
    render(<ResetButton disabled={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Reset selectors" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Selectors reset (v4)"));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/admin\/reset$/);
    expect(init.method).toBe("POST");
  });

  it("shows the backend's own reason when it refuses", async () => {
    vi.stubGlobal("fetch", reply(409, { detail: "A recovery is running; retry when it finishes" }));
    render(<ResetButton disabled={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Reset selectors" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("A recovery is running"));
  });

  it("is disabled while a workflow is running", () => {
    render(<ResetButton disabled />);
    expect(screen.getByRole("button", { name: "Reset selectors" })).toBeDisabled();
  });
});
