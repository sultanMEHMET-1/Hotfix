import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cfg = vi.hoisted(() => ({ useMocks: true }));
vi.mock("../config", () => ({
  get USE_MOCKS() {
    return cfg.useMocks;
  },
  API_BASE: "",
  RUN_WORKFLOW_PATH: "/api/v1/run-workflow",
  SENTRY_ORG: "",
}));

import { FAST_DELAY_MS, HEAL_DELAY_MS } from "../api/mocks";
import { DEFAULT_BENCHMARKS, HISTORY_LIMIT, useWorkflowRun } from "../hooks/useWorkflowRun";

const advance = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });

beforeEach(() => {
  cfg.useMocks = true;
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useWorkflowRun (mock mode)", () => {
  it("starts idle with default benchmarks", () => {
    const { result } = renderHook(() => useWorkflowRun());
    expect(result.current.phase).toBe("idle");
    expect(result.current.result).toBeNull();
    expect(result.current.history).toEqual([]);
    expect(result.current.benchmarks).toEqual({ fastMs: 310, healMs: 12400, fastCost: 0, healCost: 0.0381 });
  });

  it("fast path: running-fast -> done", async () => {
    const { result } = renderHook(() => useWorkflowRun());
    act(() => result.current.trigger({ simulateHeal: false }));
    expect(result.current.phase).toBe("running-fast");
    await advance(FAST_DELAY_MS);
    expect(result.current.phase).toBe("done");
    expect(result.current.result?.status).toBe("success");
    expect(result.current.history).toHaveLength(1);
    expect(result.current.history[0].costUsd).toBe(0);
    expect(result.current.benchmarks.fastMs).toBe(310);
  });

  it("simulated heal: running-healing immediately -> done, updates history and benchmarks", async () => {
    const { result } = renderHook(() => useWorkflowRun());
    act(() => result.current.trigger({ simulateHeal: false }));
    await advance(FAST_DELAY_MS);

    act(() => result.current.trigger({ simulateHeal: true }));
    expect(result.current.phase).toBe("running-healing");
    await advance(HEAL_DELAY_MS - 1);
    expect(result.current.phase).toBe("running-healing");
    await advance(1);
    expect(result.current.phase).toBe("done");
    expect(result.current.result?.status).toBe("healed");
    expect(result.current.history.map((h) => h.response.status)).toEqual(["healed", "success"]);
    expect(result.current.history[0].costUsd).toBe(0.0381);
    expect(result.current.benchmarks).toEqual({ fastMs: 310, healMs: 12400, fastCost: 0, healCost: 0.0381 });
  });

  it("re-trigger aborts the in-flight run and ignores its result", async () => {
    const { result } = renderHook(() => useWorkflowRun());
    act(() => result.current.trigger({ simulateHeal: true }));
    await advance(1000);
    act(() => result.current.trigger({ simulateHeal: false }));
    await advance(HEAL_DELAY_MS);
    expect(result.current.history).toHaveLength(1);
    expect(result.current.history[0].response.status).toBe("success");
    expect(result.current.phase).toBe("done");
  });

  it("caps history at 20, newest first", async () => {
    const { result } = renderHook(() => useWorkflowRun());
    for (let i = 0; i < HISTORY_LIMIT + 2; i++) {
      act(() => result.current.trigger({ simulateHeal: false }));
      await advance(FAST_DELAY_MS);
    }
    expect(result.current.history).toHaveLength(HISTORY_LIMIT);
    const ids = new Set(result.current.history.map((h) => h.response.trace_id));
    expect(ids.size).toBe(HISTORY_LIMIT);
  });
});

describe("useWorkflowRun (live mode)", () => {
  beforeEach(() => {
    cfg.useMocks = false;
  });

  it("switches running-fast -> running-healing after 1s, then uses live numbers for benchmarks", async () => {
    let resolveFetch!: (r: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((r) => (resolveFetch = r))),
    );
    const { result } = renderHook(() => useWorkflowRun());
    act(() => result.current.trigger({ simulateHeal: false }));
    expect(result.current.phase).toBe("running-fast");
    await advance(999);
    expect(result.current.phase).toBe("running-fast");
    await advance(1);
    expect(result.current.phase).toBe("running-healing");

    await act(async () => {
      resolveFetch(
        new Response(
          JSON.stringify({
            status: "healed",
            execution_time_ms: 9000,
            data: { cost_usd: 0.05 },
            healed: true,
            trace_id: "b".repeat(32),
            diff: { old_selector: "#a", new_selector: "#b" },
          }),
          { status: 200 },
        ),
      );
    });
    expect(result.current.phase).toBe("done");
    expect(result.current.benchmarks).toEqual({ ...DEFAULT_BENCHMARKS, healMs: 9000, healCost: 0.05 });
  });

  it("reports errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 500 })));
    const { result } = renderHook(() => useWorkflowRun());
    act(() => result.current.trigger({ simulateHeal: false }));
    await advance(0);
    expect(result.current.phase).toBe("error");
    expect(result.current.error?.message).toMatch(/500/);
    expect(result.current.history).toEqual([]);
  });

  it("aborts the request on unmount", async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_u: string, init: RequestInit) => {
        signal = init.signal ?? undefined;
        return new Promise<Response>(() => {});
      }),
    );
    const { result, unmount } = renderHook(() => useWorkflowRun());
    act(() => result.current.trigger({ simulateHeal: false }));
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});
