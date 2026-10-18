import { failedCopy } from "../components/StatusBadge";
import { describe, expect, it } from "vitest";
import type { WorkflowExecutionResponse } from "@contracts/api_types";
import { executionPathLabel, runCostUsd, usedAgent } from "../lib/cost";
import { formatMs, formatUsd } from "../lib/format";
import { sentryTraceUrl } from "../lib/sentry";

type R = Pick<WorkflowExecutionResponse, "healed" | "recovery_attempted" | "agent_cost_usd">;

describe("usedAgent / executionPathLabel", () => {
  it("uses recovery_attempted when present", () => {
    expect(usedAgent({ healed: false, recovery_attempted: true })).toBe(true);
    expect(usedAgent({ healed: true, recovery_attempted: false })).toBe(false);
  });
  it("falls back to healed for legacy responses", () => {
    expect(usedAgent({ healed: true })).toBe(true);
    expect(usedAgent({ healed: false })).toBe(false);
  });
  it("labels the path", () => {
    expect(executionPathLabel({ healed: false })).toBe("Deterministic Playwright");
    expect(executionPathLabel({ healed: false, recovery_attempted: true })).toBe("Browser Use Agent Engaged");
  });
});

describe("runCostUsd", () => {
  it("is 0 for a deterministic run", () => {
    expect(runCostUsd({ healed: false } satisfies R)).toBe(0);
  });
  it("uses agent_cost_usd for agent runs, including a measured zero", () => {
    expect(runCostUsd({ healed: true, recovery_attempted: true, agent_cost_usd: 0.002 })).toBe(0.002);
    expect(runCostUsd({ healed: false, recovery_attempted: true, agent_cost_usd: 0 })).toBe(0);
  });
  it("is unknown (null), never 0, when an agent run omits its cost", () => {
    expect(runCostUsd({ healed: false, recovery_attempted: true })).toBeNull();
    expect(runCostUsd({ healed: true, recovery_attempted: true, agent_cost_usd: null })).toBeNull();
    expect(runCostUsd({ healed: true })).toBeNull();
  });
});

describe("sentryTraceUrl", () => {
  it("builds the trace URL", () => {
    expect(sentryTraceUrl("abc123", "mender")).toBe("https://mender.sentry.io/explore/traces/trace/abc123/");
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
    expect(formatUsd(null)).toBe("Unknown");
  });
});

describe("failedCopy", () => {
  const base = { status: "failed", execution_time_ms: 1, data: {}, healed: false, trace_id: "t" } as const;
  const record: Record<string, unknown> = { field: "f", diff: { old_selector: "a", new_selector: "b" }, evidence: {}, version_before: 1 };

  it("only claims a revert when a rolled back record exists", () => {
    const rolled = { ...record, verification_outcome: "rolled_back" } as never;
    expect(failedCopy({ ...base, recovery_attempted: true, heal_records: [rolled] })).toBe("Reverted after a failed recovery");
    expect(failedCopy({ ...base, recovery_attempted: true })).toBe("Recovery failed, no selector changed");
    expect(failedCopy({ ...base, recovery_attempted: false })).toBe("Run failed before recovery");
  });

  it("names a sign-in wall when the agent was blocked", () => {
    expect(failedCopy({ ...base, recovery_attempted: true, error: { code: "agent_blocked", message: "x" } })).toBe("Blocked by a sign-in wall, nothing changed");
  });

  it("never says nothing changed when the rollback itself failed", () => {
    const text = failedCopy({ ...base, recovery_attempted: true, error: { code: "rollback_failed", message: "x" } });
    expect(text).toMatch(/Rollback failed/);
  });
});

import { workflowLabel } from "../lib/workflowLabel";
import { formatDuration } from "../lib/format";

describe("workflowLabel", () => {
  it("names the demo sites, and spaces out any other id", () => {
    expect(workflowLabel("permit-application")).toBe("Permit portal");
    expect(workflowLabel("record-update")).toBe("Inventory desk");
    expect(workflowLabel("wikipedia-article")).toBe("Wikipedia");
    expect(workflowLabel("python-latest-release")).toBe("Python releases");
    expect(workflowLabel("books-travel-first-book")).toBe("Books");
    expect(workflowLabel("quotes-love-first-quote")).toBe("Quotes");
    expect(workflowLabel("new-site-check")).toBe("New site check");
  });
});

describe("formatDuration", () => {
  it("uses milliseconds under a second, seconds under a minute, then minutes", () => {
    expect(formatDuration(125)).toBe("125 ms");
    expect(formatDuration(999)).toBe("999 ms");
    expect(formatDuration(999.6)).toBe("1.0 s");
    expect(formatDuration(1000)).toBe("1.0 s");
    expect(formatDuration(4200)).toBe("4.2 s");
    expect(formatDuration(59940)).toBe("59.9 s");
    expect(formatDuration(59960)).toBe("1 m 0 s");
    expect(formatDuration(72000)).toBe("1 m 12 s");
  });
});
