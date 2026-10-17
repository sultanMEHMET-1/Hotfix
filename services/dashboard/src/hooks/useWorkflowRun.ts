import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { WorkflowExecutionResponse } from "@contracts/api_types";
import { runWorkflow } from "../api/client";
import { USE_MOCKS } from "../config";
import { AGENT_RUN_COST_USD, runCostUsd } from "../lib/cost";

export type RunPhase = "idle" | "running-fast" | "running-healing" | "done" | "error";

export interface RunHistoryEntry {
  id: string;
  /** Epoch ms when the run was triggered. */
  startedAt: number;
  response: WorkflowExecutionResponse;
  costUsd: number;
}

export interface Benchmarks {
  fastMs: number;
  healMs: number;
  fastCost: number;
  healCost: number;
}

export interface TriggerOptions {
  simulateHeal: boolean;
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
export const DEFAULT_BENCHMARKS: Benchmarks = {
  fastMs: 310,
  healMs: 12400,
  fastCost: 0,
  healCost: AGENT_RUN_COST_USD,
};

export function computeBenchmarks(history: RunHistoryEntry[]): Benchmarks {
  const fast = history.find((h) => h.response.status === "success");
  const heal = history.find((h) => h.response.status === "healed");
  return {
    fastMs: fast ? fast.response.execution_time_ms : DEFAULT_BENCHMARKS.fastMs,
    healMs: heal ? heal.response.execution_time_ms : DEFAULT_BENCHMARKS.healMs,
    fastCost: fast ? fast.costUsd : DEFAULT_BENCHMARKS.fastCost,
    healCost: heal ? heal.costUsd : DEFAULT_BENCHMARKS.healCost,
  };
}

function isAbortError(e: unknown): boolean {
  return typeof e === "object" && e !== null && (e as { name?: unknown }).name === "AbortError";
}

let entrySeq = 0;

export function useWorkflowRun(): UseWorkflowRun {
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
    ({ simulateHeal }: TriggerOptions) => {
      cancelInFlight();
      const runId = ++runIdRef.current;
      const controller = new AbortController();
      controllerRef.current = controller;
      const startedAt = Date.now();

      setError(null);
      if (USE_MOCKS && simulateHeal) {
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

      runWorkflow({ simulateHeal, signal: controller.signal }).then(
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

  const benchmarks = useMemo(() => computeBenchmarks(history), [history]);

  return { phase, result, error, history, benchmarks, trigger };
}
