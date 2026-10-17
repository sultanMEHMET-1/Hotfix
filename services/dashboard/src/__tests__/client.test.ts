import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cfg = vi.hoisted(() => ({ useMocks: true }));
vi.mock("../config", () => ({
  get USE_MOCKS() {
    return cfg.useMocks;
  },
  API_BASE: "http://api.test",
  RUN_WORKFLOW_PATH: "/api/v1/run-workflow",
  SENTRY_ORG: "",
}));

import { runWorkflow } from "../api/client";
import { FAST_DELAY_MS, HEAL_DELAY_MS, fastResponse, healResponse, mockRunWorkflow } from "../api/mocks";

const HEX32 = /^[0-9a-f]{32}$/;

describe("mock responses", () => {
  it("match the contract fixtures", () => {
    expect(fastResponse).toMatchObject({
      status: "success",
      healed: false,
      execution_time_ms: 310,
      data: { workflow_id: "permit-application", permit_status: "submitted" },
    });
    expect(fastResponse.diff).toBeUndefined();
    expect(healResponse).toMatchObject({
      status: "healed",
      healed: true,
      execution_time_ms: 12400,
      data: { cost_usd: 0.0381 },
      diff: { old_selector: "#submit-btn", new_selector: 'button[data-action="submit"]' },
    });
  });
});

describe("runWorkflow (mock mode)", () => {
  beforeEach(() => {
    cfg.useMocks = true;
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("resolves the fast response after FAST_DELAY_MS with a fresh trace id", async () => {
    let settled = false;
    const p = runWorkflow().then((r) => {
      settled = true;
      return r;
    });
    await vi.advanceTimersByTimeAsync(FAST_DELAY_MS - 1);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    const r = await p;
    expect(r.status).toBe("success");
    expect(r.trace_id).toMatch(HEX32);

    const p2 = runWorkflow();
    await vi.advanceTimersByTimeAsync(FAST_DELAY_MS);
    expect((await p2).trace_id).not.toBe(r.trace_id);
  });

  it("resolves the heal response after HEAL_DELAY_MS", async () => {
    let settled = false;
    const p = runWorkflow({ simulateHeal: true }).then((r) => {
      settled = true;
      return r;
    });
    await vi.advanceTimersByTimeAsync(HEAL_DELAY_MS - 1);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    const r = await p;
    expect(r.status).toBe("healed");
    expect(r.diff?.new_selector).toBe('button[data-action="submit"]');
    expect(r.trace_id).toMatch(HEX32);
  });

  it("rejects with AbortError when aborted", async () => {
    const c = new AbortController();
    const p = mockRunWorkflow(true, c.signal);
    const assertion = expect(p).rejects.toMatchObject({ name: "AbortError" });
    c.abort();
    await assertion;
  });
});

describe("runWorkflow (live mode)", () => {
  beforeEach(() => {
    cfg.useMocks = false;
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    cfg.useMocks = true;
  });

  it("POSTs the workflow id and returns the parsed response", async () => {
    const body = {
      status: "success",
      execution_time_ms: 280,
      data: { permit_status: "submitted" },
      healed: false,
      trace_id: "a".repeat(32),
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const c = new AbortController();

    const r = await runWorkflow({ signal: c.signal });

    expect(r).toEqual(body);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/run-workflow");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ workflow_id: "permit-application" });
    expect(init.signal).toBe(c.signal);
  });

  it("throws a descriptive error on non-2xx", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("boom", { status: 502, statusText: "Bad Gateway" })));
    await expect(runWorkflow()).rejects.toThrow(/502.*Bad Gateway.*boom/);
  });

  it("throws when required fields are missing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "success" }), { status: 200 })));
    await expect(runWorkflow()).rejects.toThrow(/execution_time_ms.*data.*healed.*trace_id/);
  });
});
