# M2 review handoff

## Status and review boundary

M1 was accepted; M2 is implemented on `codex/browser-use-recovery` and must stop
for review. The pre-M2 baseline is `e88872e`. M3 cooldown and populated
`heal_records` are not implemented. No real team portal, runner, or dashboard is
present in this checkout; integration fixtures are not replacements for them.

The endpoint keeps the shared response model and schema. The user's latest
instruction deliberately withholds `error`, `agent_cost_usd`,
`agent_duration_ms`, and `heal_records` from responses, even though the shared
model currently permits them. Failed execution returns `status="failed"`,
`healed=false`, and `data={}`. Detail, cost, and token usage belong in logs and
Sentry. Do not re-enable those response fields without owner approval.

## Read and trace

| Source | Responsibility and review focus |
| --- | --- |
| [main.py](main.py) | Startup validation, bounded fast-path lock acquisition, active-task joining, shielded waiting, each waiter's own replay, response omission policy. |
| [recovery.py](recovery.py) | Application-owned tasks, one baseline, three-invocation loop, ordered progress, deadline, final canary, rollback, measurement accounting. |
| [healer.py](healer.py) | Lazy SDK imports, Gemini, executed-history grounding, live CSS capture, browser and cached Google client cleanup. |
| [runner.py](runner.py) | CLI subprocess, separate stdout/stderr, per-operation/deadline timeouts, process-group termination, raw output validation, owned artifacts. No selector locks. |
| [store.py](store.py) | POSIX locks, validated atomic writes, backups, higher-version restoration. |
| [config.py](config.py) | Backend workflow definitions, ordered steps, top-level goal, schemas, canary masking, runtime settings. |
| [terminal.py](terminal.py) | Rich rendering without emojis; original records and telemetry are preserved. |
| [reset.py](reset.py) | Operator reset using the same lock and higher-version restoration. |

## Recovery state and invariants

1. Startup loads workflows and schemas. The configured demo workflow, defaulting
   to the selector map's workflow ID, requires a canary. Missing runner or workflow
   configuration remains an explicit 503. Invalid parameters return 422.
2. If a workflow has an active recovery, join it. Otherwise acquire the shared
   lock within five seconds, validate map compatibility, and run deterministic
   execution. Keep the lock for that execution, but bound only acquisition.
3. Runner failure needs valid, run-owned evidence before recovery. Register an
   application-owned task without an intervening await. Existing waiters share
   its result. A request cancellation must not cancel the task.
4. Recovery starts its 240-second clock at task creation, before exclusive-lock
   waiting. Work stops after 210 seconds; 30 seconds remain for emergency cleanup
   and rollback. The initial fast run and any waiter's final replay are outside
   this recovery clock. Local tests use shorter injected Settings values.
5. Under the exclusive lock, reread selectors and replay if another writer
   changed them. Then validate workflow, field, expected selector, and origin;
   save exactly one baseline backup before the first agent attempt.
6. Invoke Browser Use at most three times. Agent errors/timeouts/no-result may
   retry the same field. Ambiguous evidence, invalid candidates, and cleanup
   failures are terminal. SDK-internal retries do not reset this backend cap.
7. Ground each candidate in one executed action/result/element match. CSS comes
   from stable attributes, a unique tag, or live structural targeting. An agent
   completion statement is never sufficient. No mutable class or XPath is stored.
8. Write each candidate atomically at the next version. Replay under the lock
   already held; Runner.execute must never reacquire it. A valid later-step
   failure retains provisional progress; same/earlier failures abort. Three
   attempts exhausted also abort.
9. Final replay output must pass JSON Schema. Run a separate canary, validate raw
   output, then compare after explicit volatile-field exclusions. Commit only
   after all checks pass. Generic non-demo definitions may omit a canary.
10. Any terminal failure restores the entire baseline if a patch was installed.
    Restoration uses a new version greater than every provisional version. No
    installed patch means no restoration write. Rollback failure blocks service.
11. Successful waiters replay with their own parameters/run IDs; failed flights
    return failure to existing waiters. Completed tasks are removed immediately.
    There is no cooldown or persistent success/failure cache.
12. Emit one measurement record per recovery. Independent background Sentry
    transactions retain the originating trace ID and can finish after the owner
    request closes. Waiter spans retain a recovery trace reference.

All selector writers must follow the lock protocol, including reset. Outside
editors do not automatically participate. Graceful application shutdown drains
active tasks. Client/proxy timeouts must cover at least 240 seconds plus initial
execution, waiter replay, and network overhead. A timeout is not a reset request.

## SDK evidence and derivation

Verified runtime: Python 3.12.2 and browser-use 0.13.11. Gemini uses native
`ChatGoogle`, with model/key from the environment. The wrapper requires
`max_retries >= 1`; the adapter uses 1, six steps, one action per step, and one
consecutive failure before stopping. Browser Use remains absent on fast success.

The recorded history fixture projects a real Browser Use/Chrome run driven by
scripted model responses. It supports unique input/button grounding and retains
executed results, attributes, accessible names, and XPath. It establishes SDK
history shape, not model reasoning. Paid local tests separately exercise Gemini.

Candidate order is `data-testid`, `data-test`, `data-action`, `data-field`, `id`,
`name`, `aria-label`, a unique tag, then ancestor/direct-child/`:nth-of-type()`
structure. Every candidate is checked against the exact live node before capture.
Classes are ignored. Structural CSS may break if the page is reordered later.
Missing or unsupported live targets fail explicitly and cannot authorize a write.

Emergency browser cleanup depends on the pinned SDK's private local-browser
watchdog PID. Only its owned process tree is targeted. Review this on upgrades.
ChatGoogle caches a Google client; close both async and sync clients after every
invocation. A real live run exposed unclosed transport warnings before this fix.

## Tests and evidence

Commands are in [README.md](README.md). The ordinary suite makes no model calls.
Real-DOM checks require `MENDER_BROWSER_TEST=1` and live dependencies. Paid tests
require `MENDER_LIVE_TEST=1`; all portal/maps/screenshots/backups are temporary.
Sanitized live measurement JSON is retained under ignored backend `state/`.

Primary [M2 checks](tests/test_m2.py):

- `test_two_fields_repair_in_order_without_reentrant_deadlock`: exact ordered
  repairs and only two lock acquisitions, shared then exclusive. An outer
  timeout catches a re-entrant deadlock; replay and canary actually execute.
- `test_canary_failure_restores_both_patches_with_higher_version`: version
  1 -> 2 -> 3 -> restored 4, with original fields and no committed diff.
- `test_later_repair_failure_restores_first_patch`: earlier progress disappears
  when later agent retries exhaust; no fourth invocation.
- `test_deadline_during_agent_restores_first_patch`: shared deadline interrupts
  an agent after a provisional write and restores the baseline.
- `test_request_cancellation_after_first_patch_preserves_background_and_waiter`:
  cancels an ASGI request task and verifies ongoing recovery plus waiter-owned
  parameters and output. This is not a real TCP-disconnect test.
- Retry, no-result, ambiguity, invalid candidate, schema rejection, bounded lock
  waiting, shared lock deadline, missing canary, runner-spawn cancellation, and failed active-flight tests
  exercise additional boundaries. Failed-flight tests explicitly prove no cooldown.

[Real DOM checks](tests/test_selectors.py) mutate classes, exercise stable and
structural selectors, escape quotes/backslashes/international attributes, and
reject a missing live target. [M1 checks](tests/test_m1.py) retain regression
coverage for malformed artifacts, cleanup, rollback failure, atomic-write
failure, canary masking, tracing, reset, and the import boundary. Their response
assertions now follow the user's withheld-field policy. Contract tests remain
unchanged; terminal tests still preserve literal selectors and original records.

### Live measurements

Original retained M1 log: request 24.300 s, entire unittest 27.978 s; tokens and
agent-only wall time were not retained and cannot be reconstructed.

First instrumented M2 sample, actual Gemini against the localhost fixture:

| Scenario | Request | Recovery | Entire test | Prompt / completion tokens | Total tokens |
| --- | --- | --- | --- | --- | --- |
| Button | 19.588 s | 16.907 s | 21.948 s | 21,823 / 1,288 | 23,111 |
| Two fields | 38.247 s | 35.669 s | 38.708 s | 43,638 / 3,254 | 46,892 |

Both used gemini-3.8-flash, Python 3.12.2, browser-use 0.13.11, and local Chrome.
SDK estimated costs were $0.02119725 and $0.044931, respectively. These are SDK
estimates, not billing receipts. Cached prompt tokens were zero. Tokens follow
the SDK's prompt-plus-completion convention; reasoning-token billing is not
independently reconciled. Single samples do not establish a latency percentile.

Final verification after explicit Google client cleanup:

| Scenario | Backend request | Recovery | Entire test | Agent invocations | Prompt / completion | Total tokens |
| --- | --- | --- | --- | --- | --- | --- |
| Button | 20.743 s | 17.990 s | 23.076 s | 1, taking 16.788 s | 21,814 / 1,509 | 23,323 |
| Two fields | 38.668 s | 36.096 s | 39.140 s | 2, taking 15.665 s and 16.635 s | 43,612 / 2,813 | 46,425 |

SDK estimated costs were $0.02201925 and $0.04325775. Both runs had complete
SDK token summaries and zero cached prompt tokens. Both committed, with selector
versions 2 and 3 respectively. The final live capture had no unclosed-transport
warnings; the installed Google dependency still emits a deprecation warning.

Retained final reports (ignored local artifacts):

- `state/live-button-e4c2d555-f770-47ad-a8d7-0a47562a61e2.json`
- `state/live-two-fields-da1a6595-4e04-41fc-b1cc-05814c0d07be.json`

Default suite: **64 tests, 57 passed and 7 opt-in tests skipped**. The final
combined live/real-DOM command ran **7 tests, all passed**. It enabled both
`MENDER_LIVE_TEST=1` and `MENDER_BROWSER_TEST=1` and selected
`services.backend.tests.test_live services.backend.tests.test_selectors`.
Static `ruff --isolated --select E4,E7,E9,F` and `git diff --check` also passed.

Adversarial mutation checks ran in an isolated test process without editing
source: replacing restoration with a no-op made the canary rollback test fail;
forcing every ordered-step position to zero made the two-field test fail.
Both expected failures were detected, proving those acceptance checks can reject
broken implementations. Mutation patches were removed before normal verification.

## Remaining limits

- M3 cooldown and heal records remain absent. A request after a failed task has
  finished may start a new recovery immediately.
- No automatic crash recovery. Forced termination after a provisional write
  may leave it installed; preserve backups and use reset, then restart.
- The deadline assumes a responsive process/OS. Synchronous filesystem work
  cannot be preempted by asyncio. Cleanup overruns or failures block the backend;
  the 240-second ceiling is not a guarantee against an OS stall or forced kill.
- POSIX locks/process groups, one Uvicorn worker, and one configured selector map
  remain demo constraints. This is not a multi-worker distributed coordinator.
- Subprocess stdout/stderr are buffered in memory. Output-volume limits and load
  testing are not implemented. Read-only result extraction and iframes remain
  unsupported; duplicate/dynamic labels may explicitly fail grounding.
- Person 1 still needs to supply the real runner, artifacts, and approximately
  two-second per-step selector timeouts. The real read-only workflow definition,
  representative canary, and actual portal URL are still team dependencies.
- Local fixture measurements do not prove real portal latency or the 400 ms
  fast-path target. Live Sentry delivery, its UI presentation, and portal Session
  Replay remain unverified; in-memory trace/grouping checks are narrower evidence.

If restoration or cleanup fails, inspect the logged reason, preserve the baseline,
stop owned resources, reset under the same lock, and restart before retrying.
