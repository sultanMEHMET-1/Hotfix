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
import {
  FAST_DELAY_MS,
  HEAL_DELAY_MS,
  fastResponse,
  healResponse,
  mockRunWorkflow,
  rollbackResponse,
} from "../api/mocks";
import successFixture from "@contracts/fixtures/workflow_success.json";
import healedFixture from "@contracts/fixtures/workflow_healed.json";
import rolledBackFixture from "@contracts/fixtures/workflow_rolled_back.json";

const HEX32 = /^[0-9a-f]{32}$/;

describe("mock responses", () => {
  it("are the contract fixtures", () => {
    expect(fastResponse).toEqual(successFixture);
    expect(healResponse).toEqual(healedFixture);
    expect(rollbackResponse).toEqual(rolledBackFixture);
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
    const p = runWorkflow({ scenario: "heal" }).then((r) => {
      settled = true;
      return r;
    });
    await vi.advanceTimersByTimeAsync(HEAL_DELAY_MS - 1);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    const r = await p;
    expect(r.status).toBe("healed");
    expect(r.diff).toEqual(healedFixture.diff);
    expect(r.heal_records).toHaveLength(2);
    expect(r.trace_id).toMatch(HEX32);
  });

  it("resolves the rolled-back failure after HEAL_DELAY_MS", async () => {
    const p = runWorkflow({ scenario: "rollback" });
    await vi.advanceTimersByTimeAsync(HEAL_DELAY_MS);
    const r = await p;
    expect(r.status).toBe("failed");
    expect(r.error?.code).toBe("canary_mismatch");
    expect(r.heal_records?.every((h) => h.verification_outcome === "rolled_back")).toBe(true);
  });

  it("returns a copy, so callers cannot mutate the fixtures", async () => {
    const p = runWorkflow({ scenario: "heal" });
    await vi.advanceTimersByTimeAsync(HEAL_DELAY_MS);
    const r = await p;
    r.heal_records![0].field = "changed";
    expect(healResponse.heal_records![0].field).toBe("input_permit_id");
  });

  it("rejects with AbortError when aborted", async () => {
    const c = new AbortController();
    const p = mockRunWorkflow("heal", c.signal);
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

  it("accepts the recovery fields and rejects malformed ones", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(rolledBackFixture), { status: 200 })));
    await expect(runWorkflow()).resolves.toEqual(rolledBackFixture);

    const bad = { ...healedFixture, recovery_attempted: "yes", agent_cost_usd: "0.1", heal_records: [{}] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(bad), { status: 200 })));
    await expect(runWorkflow()).rejects.toThrow(/recovery_attempted.*heal_records.*agent_cost_usd/);
  });
});
