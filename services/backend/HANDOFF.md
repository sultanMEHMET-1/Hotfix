# M1 review handoff

## Status and review boundary

Implementation baseline: commit `da539ab`, branch `codex/browser-use-recovery`.
M1 repairs one field with one Browser Use agent attempt per request. It has
passed local verification and awaits review. This is not approval to begin M2
or M3, and the full team integration has not been exercised.

The shared response contract already supports future recovery records. M1 uses
`status`, `execution_time_ms`, `data`, `healed`, `trace_id`, optional `diff`,
`recovery_attempted`, structured `error`, and available agent metrics. It does
not populate `heal_records`. Default and unset fields may be omitted by FastAPI;
consumers must follow the defaults documented in the shared contract.

## Read the implementation in this order

| Source | Responsibility and review focus |
| --- | --- |
| [config.py](config.py) | `Settings`, `Workflow`, `Step`, and `Canary`; workflow discovery, JSON Schema validators, and canary masking. No permit-specific code. |
| [main.py](main.py) | `create_app` and its `run_workflow` route; request validation, locking, baseline backup, candidate verification, rollback, response, and Sentry context. |
| [runner.py](runner.py) | `Runner.execute`; argv-only subprocess calls, timeout/cancellation cleanup, strict output validation, and run-specific failure artifacts. |
| [healer.py](healer.py) | `diagnose`, `extract_evidence`, and `close_browser`; live Gemini/Browser Use, field grounding, CSS candidates, and browser cleanup. |
| [store.py](store.py) | `SelectorStore` and `atomic_json`; POSIX file locks, same-directory temporary file plus replace, backups, and versioned restoration. |
| [reset.py](reset.py) | Operator reset through the same validation and exclusive lock. |

There is no existing Person 1 runner to call or dashboard to inspect in this
checkout. The runner files under [tests/fixtures](tests/fixtures) are test
doubles and local integration fixtures, not replacements for that team's code.

## Actual request and recovery flow

1. Startup loads schemas and workflow definitions. Request parameters must pass
   the selected workflow schema. Missing definitions/runner or incompatible
   selector configuration returns 503; unknown workflows return 404; invalid
   input returns 422.
2. Under a shared selector lock, invoke the runner with a fresh UUID. Exit zero
   is success only if stdout is one JSON object matching the output schema.
3. On failure, accept only a schema-valid payload for this workflow and its own
   `runs/<run_id>/failure.png`. Failure without usable evidence returns a failed
   execution response instead of guessing a repair.
4. Acquire the exclusive lock and reread selectors. If another repair changed
   the map, replay it first. A successful replay needs no new agent run.
5. Check the failed field, old selector, and portal origin. Back up the baseline
   under backend `state/`. Hold the exclusive lock through the rest of recovery.
6. Lazily import the healer and Browser Use off the event loop. Run the agent on
   the live portal using top-level workflow `goal` plus request parameters.
7. The pre-action callback checks unique CSS against the live node. After the
   run, correlate history actions, corresponding results, interacted elements,
   role/label, and ordered workflow position. Require a unique match and its
   captured CSS. Planned actions or the agent's final answer are insufficient.
8. Atomically write the candidate at the next version. Replay the original
   request and validate its raw output. When configured, run a separate canary,
   validate its raw output, then compare after explicit volatile-field masking.
9. Return healed only after verification passes. On failure after installation,
   restore baseline contents at a new higher version. If restoration fails,
   mark the server unavailable rather than allowing further execution.

Locks prevent other backend requests from reading a provisional map, but this
also blocks their fast path while healing runs. All processes writing selectors,
including reset, must follow the backend's lock protocol. Independent tools
editing the selector file do not participate automatically.

## SDK assumptions and evidence

- Browser Use is pinned to `0.13.11`; Gemini uses its native `ChatGoogle` wrapper
  with an environment-provided model and key. The configured model during the
  successful live check was `gemini-3.8-flash`.
- The wrapper requires `max_retries >= 1`. M1 uses 1, one action per step, six
  agent steps, and one consecutive failure before stopping. Do not interpret
  SDK retry settings as the future backend's three-attempt recovery policy.
- `model_actions()` alone does not pair action results with element evidence.
  Inspect serialized history's action, result, and interacted-element arrays.
- Live CSS capture uses Browser Use's DOM snapshot and CDP session before the
  action can navigate away. The post-run extractor accepts only corresponding
  executed evidence. A Browser Use upgrade needs a fresh compatibility check.
- Emergency cleanup depends on the pinned SDK's private local-browser watchdog
  and its owned PID. Review this dependency when changing SDK versions.
- Cost is emitted only for available, finite, positive SDK pricing data;
  zero is treated conservatively as unavailable. Agent duration measures SDK
  step time, not browser startup, queueing, or end-to-end request latency.

## Verification record and review targets

At the implementation baseline, the default suite ran 31 tests: 30 passed and
the opt-in live test was skipped. The live test passed separately on macOS with
local Google Chrome. No tests called the real team portal or runner.

| Claim to challenge | Relevant checks in [test_m1.py](tests/test_m1.py) |
| --- | --- |
| An agent claim cannot install an incorrect selector | `test_wrong_selector_rolls_back_as_a_higher_version`, `test_schema_valid_wrong_data_fails_canary` |
| Missing/ambiguous history cannot identify a field | `test_ambiguous_failed_and_unexecuted_actions_are_rejected`, `test_ambiguous_agent_history_is_rejected_and_cleaned` |
| Input and button history retain usable evidence | `test_recorded_input_and_button_map_to_executed_results`, `test_mocked_agent_history_is_grounded_and_browser_is_cleaned` |
| Failure paths preserve the baseline | `test_cancellation_during_verification_restores_baseline`, `test_canary_timeout_rolls_back`, `test_failed_atomic_replace_preserves_baseline` |
| A failed rollback cannot silently resume service | `test_failed_rollback_stops_subsequent_execution` |
| Concurrent requests cannot use provisional selectors | `test_overlapping_requests_cannot_consume_a_provisional_map` |
| Process and browser cleanup happen | `test_runner_timeout_kills_process`, `test_agent_timeout_always_cleans_browser`, `test_failed_sdk_cleanup_force_kills_its_owned_process` |
| The fast path avoids Browser Use | `test_app_import_does_not_import_browser_use_or_healer`, `test_fast_success_never_invokes_healer` |
| Errors group and responses correlate with traces | `test_sentry_fingerprint_spans_and_trace_correlation` |
| Reset follows version semantics | `test_reset_uses_backup_and_increments_version` |

[test_contracts.py](tests/test_contracts.py) also checks model/schema agreement,
response fixtures, legacy response compatibility, and invalid recovery metadata.
[test_live.py](tests/test_live.py) uses actual Gemini, Browser Use, and a real
Playwright subprocess replay and canary against a temporary localhost portal.
All live-test selectors, backups, and workflow definitions are temporary.

The [recorded history fixture](tests/fixtures/recorded_history.json) is a reduced
projection of a real Browser Use/Chrome run using scripted model responses. It
is evidence about SDK history shape, not proof of model reasoning quality.

Use the commands in [README.md](README.md) to reproduce default tests, opt-in
live verification, startup, and reset. The documented Uvicorn invocation was
also checked: it serves OpenAPI and returns an explicit 503 with this checkout's
missing workflow definitions. Static checks passed with:

```sh
uvx ruff check --isolated --select E4,E7,E9,F services/backend
git diff --check
```

## Known gaps and integration dependencies

- **M2 is absent:** no accumulated multi-field patches, three-attempt loop, or
  monotonic 240-second recovery deadline. In M1, a later-step replay failure
  causes rollback rather than preserving provisional progress.
- **M3 is absent:** no shared recovery task, failure cooldown, joined-request
  accounting, or populated heal-record list. A failed repair can be repeated
  by the next waiting request. A lock and map recheck are not full single-flight.
- **Timeouts are not an end-to-end ceiling:** runner calls default to 45 seconds,
  agent diagnosis to 90, and browser shutdown to 15 before emergency cleanup.
  Lock waiting and the complete request do not yet have one shared deadline.
- **Crash recovery is absent:** exception/cancellation rollback does not cover
  a process crash or forced termination after a patch. Backups exist, but the
  server does not automatically recover an interrupted transaction on startup.
- **Cancellation coverage is limited:** tests inject task cancellation during
  verification. They do not establish that an HTTP client disconnect cancels
  work, nor cover every possible cancellation timing.
- **Platform/throughput limits:** one Uvicorn worker and POSIX `fcntl`/process
  groups are assumed. This is not a Windows-compatible or multi-workflow store.
  Subprocess output is buffered in memory; only the trace's stderr copy is
  truncated. Large-output behavior has not been load-tested.
- **Extraction limits:** unique input/button evidence is exercised. Read-only
  result-element extraction and iframe targeting are unsupported. Dynamic or
  duplicate labels can correctly produce an explicit mapping failure.
- **Integration still needs owners:** Person 1 must provide the agreed runner
  CLI, per-run artifacts, and a roughly two-second per-step timeout. The team
  must supply a real read-only workflow definition and correct the current
  application-oriented selector map/example URL. Person 3 consumes the existing
  response fields without assuming future M3 fields are populated.
- **Performance/observability are not fully proven:** the 400 ms fast-path goal
  has not been benchmarked on the real runner. Sentry grouping/spans/correlation
  were checked with an in-memory transport; delivery to a real Sentry project,
  AI monitoring presentation, and portal Session Replay remain unverified.
- **No canary means schema-only semantic verification.** Schema-valid but wrong
  data may pass without a representative canary. Canary exclusions cannot
  remove all comparison, but meaningful business coverage is the owner's job.

If rollback fails, retain the baseline backup, restore it through the reset
command, and restart the server to clear its unavailable state. Source safety
claims should be reviewed against these limits, not inferred from a green test
count. Do not advance beyond the milestone review boundary automatically.
