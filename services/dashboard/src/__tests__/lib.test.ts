import { describe, expect, it } from "vitest";
import type { WorkflowExecutionResponse } from "@contracts/api_types";
import { AGENT_RUN_COST_USD, runCostUsd } from "../lib/cost";
import { formatMs, formatUsd } from "../lib/format";
import { sentryTraceUrl } from "../lib/sentry";

const res = (status: WorkflowExecutionResponse["status"], data: Record<string, unknown> = {}) => ({ status, data });

describe("runCostUsd", () => {
  it("is 0 for success even with cost_usd", () => {
    expect(runCostUsd(res("success", { cost_usd: 1 }))).toBe(0);
  });
  it("uses data.cost_usd when finite", () => {
    expect(runCostUsd(res("healed", { cost_usd: 0.05 }))).toBe(0.05);
    expect(runCostUsd(res("failed", { cost_usd: 0.02 }))).toBe(0.02);
  });
  it("falls back per status", () => {
    expect(AGENT_RUN_COST_USD).toBe(0.0381);
    expect(runCostUsd(res("healed"))).toBe(0.0381);
    expect(runCostUsd(res("healed", { cost_usd: "0.1" }))).toBe(0.0381);
    expect(runCostUsd(res("healed", { cost_usd: Number.NaN }))).toBe(0.0381);
    expect(runCostUsd(res("failed"))).toBe(0);
    expect(runCostUsd(res("failed", { cost_usd: Infinity }))).toBe(0);
  });
});

describe("sentryTraceUrl", () => {
  it("builds the trace URL", () => {
    expect(sentryTraceUrl("abc123", "mender")).toBe("https://mender.sentry.io/performance/trace/abc123/");
  });
  it("returns null when org or traceId is empty", () => {
    expect(sentryTraceUrl("abc123", "")).toBeNull();
    expect(sentryTraceUrl("", "mender")).toBeNull();
    expect(sentryTraceUrl("abc123")).toBeNull(); // SENTRY_ORG unset in tests
  });
});

describe("format", () => {
  it("formatMs", () => {
    expect(formatMs(310)).toBe("310ms");
    expect(formatMs(12400)).toBe("12,400ms");
    expect(formatMs(309.6)).toBe("310ms");
    expect(formatMs(0)).toBe("0ms");
  });
  it("formatUsd", () => {
    expect(formatUsd(0)).toBe("$0.0000");
    expect(formatUsd(0.0381)).toBe("$0.0381");
    expect(formatUsd(1.23456)).toBe("$1.2346");
  });
});
