import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as Sentry from "@sentry/react";
import type { WorkflowExecutionResponse, WorkflowSummary } from "@contracts/api_types";
import { runWorkflow } from "../api/client";
import { type MockScenario, fastResponse, healResponse } from "../api/mocks";
import { USE_MOCKS } from "../config";
import { runCostUsd, usedAgent } from "../lib/cost";

export type RunPhase = "idle" | "running-fast" | "running-healing" | "done" | "error";

export interface RunHistoryEntry {
  id: string;
  /** Epoch ms when the run was triggered. */
  startedAt: number;
  response: WorkflowExecutionResponse;
  /** null when the agent ran but the backend did not report a cost. */
  costUsd: number | null;
}

/** null means "no real run yet": the UI shows n/a instead of inventing a number. */
export interface Benchmarks {
  fastMs: number | null;
  healMs: number | null;
  fastCost: number | null;
  healCost: number | null;
}

export interface TriggerOptions {
  /** Mock mode only: which canned outcome to return. */
  scenario: MockScenario;
  /** Which workflow to run; defaults to the permit demo. */
  workflow?: WorkflowSummary;
}

export interface UseWorkflowRun {
  phase: RunPhase;
  /** Latest completed response (kept across later errors / new runs until replaced). */
  result: WorkflowExecutionResponse | null;
  /** Error from the latest run, cleared when a new run starts. */
  error: Error | null;
  /** Newest first, capped at HISTORY_LIMIT. */
  history: RunHistoryEntry[];
  benchmarks: Benchmarks;
  trigger: (opts: TriggerOptions) => void;
}

export const HISTORY_LIMIT = 20;
/** In live mode, switch from "running-fast" to "running-healing" after this long without a response. */
export const HEALING_THRESHOLD_MS = 1000;
/** Baselines from the contract fixtures, shown until real runs arrive. */
export const DEFAULT_BENCHMARKS: Benchmarks = {
  fastMs: fastResponse.execution_time_ms,
  healMs: healResponse.execution_time_ms,
  fastCost: runCostUsd(fastResponse),
  healCost: runCostUsd(healResponse),
};

/** Live mode before any real run: every figure is unknown. */
export const EMPTY_BENCHMARKS: Benchmarks = { fastMs: null, healMs: null, fastCost: null, healCost: null };

/** Real runs win; otherwise fall back to `placeholders` (fixture numbers in mock mode, n/a in live mode). */
export function computeBenchmarks(history: RunHistoryEntry[], placeholders: Benchmarks = DEFAULT_BENCHMARKS): Benchmarks {
  const fast = history.find((h) => h.response.status === "success" && !usedAgent(h.response));
  const heal = history.find((h) => h.response.status === "healed");
  return {
    fastMs: fast ? fast.response.execution_time_ms : placeholders.fastMs,
    healMs: heal ? heal.response.execution_time_ms : placeholders.healMs,
    fastCost: fast ? fast.costUsd : placeholders.fastCost,
    healCost: heal ? heal.costUsd : placeholders.healCost,
  };
}

function isAbortError(e: unknown): boolean {
  return typeof e === "object" && e !== null && (e as { name?: unknown }).name === "AbortError";
}

let entrySeq = 0;

export function useWorkflowRun(mocksOn: boolean = USE_MOCKS): UseWorkflowRun {
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [result, setResult] = useState<WorkflowExecutionResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [history, setHistory] = useState<RunHistoryEntry[]>([]);

  const runIdRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const healTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelInFlight = useCallback(() => {
    if (healTimerRef.current !== null) {
      clearTimeout(healTimerRef.current);
      healTimerRef.current = null;
    }
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  useEffect(
    () => () => {
      runIdRef.current++;
      cancelInFlight();
    },
    [cancelInFlight],
  );

  const trigger = useCallback(
    ({ scenario, workflow }: TriggerOptions) => {
      cancelInFlight();
      const runId = ++runIdRef.current;
      const controller = new AbortController();
      controllerRef.current = controller;
      const startedAt = Date.now();

      setError(null);
      if (USE_MOCKS && scenario !== "fast") {
        setPhase("running-healing");
      } else {
        setPhase("running-fast");
        healTimerRef.current = setTimeout(() => {
          healTimerRef.current = null;
          if (runIdRef.current === runId) setPhase("running-healing");
        }, HEALING_THRESHOLD_MS);
      }

      const finish = () => {
        if (healTimerRef.current !== null) {
          clearTimeout(healTimerRef.current);
          healTimerRef.current = null;
        }
        if (controllerRef.current === controller) controllerRef.current = null;
      };

      // The click is the root of one trace: the fetch below carries it into the backend, the runner and the agent.
      Sentry.startSpan(
        { name: "Trigger workflow", op: "ui.action.click",
          attributes: { "workflow.id": workflow?.id ?? "permit-application", "mender.mocks": USE_MOCKS } },
        () => runWorkflow({ scenario, workflow, signal: controller.signal }),
      ).then(
        (response) => {
          if (runIdRef.current !== runId) return;
          finish();
          const entry: RunHistoryEntry = {
            id: `${startedAt}-${++entrySeq}`,
            startedAt,
            response,
            costUsd: runCostUsd(response),
          };
          setResult(response);
          setHistory((prev) => [entry, ...prev].slice(0, HISTORY_LIMIT));
          setPhase("done");
        },
        (e: unknown) => {
          if (runIdRef.current !== runId || isAbortError(e)) return;
          finish();
          setError(e instanceof Error ? e : new Error(String(e)));
          setPhase("error");
        },
      );
    },
    [cancelInFlight],
  );

  const benchmarks = useMemo(
    () => computeBenchmarks(history, mocksOn ? DEFAULT_BENCHMARKS : EMPTY_BENCHMARKS),
    [history, mocksOn],
  );

  return { phase, result, error, history, benchmarks, trigger };
}
