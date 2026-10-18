# Backend handoff

State of `services/backend` for a teammate or agent picking it up. The run guide is
[README.md](README.md), the rules for agents are [AGENTS.md](AGENTS.md), and the project brief is
[CLAUDE.md](CLAUDE.md). M1 to M3 are merged into `main` (PR #1). Everything else below is on branch `codex/browser-use-recovery`, delivered as a PR for the user to merge.

## Status

| Area | State |
| --- | --- |
| M1 single-field recovery, M2 transactional multi-field recovery, M3 failure cooldown and finalized `heal_records` | Shipped, tested, merged |
| Real runner and portal (Person 1) | Merged; speaks the agreed CLI; verified end to end |
| Dashboard (Person 3) | Merged; verified in a real browser against the real backend |
| Generic runner and per-workflow maps | `contracts/workflows/<id>.json` + `contracts/selectors/<id>.json`; the runner navigates to the map's `target_url`; two workflows (`permit-application`, `record-update`) on one backend |
| Read healing | A broken read selector is repaired from the values the agent saw, verified by replay and the canary |
| Crash recovery, pruning | `state/inflight-<wf>.json` marker restored at startup; `runs/` keeps the newest 50 |
| Write workflows (local sites only) | Shipped with a guard, a sandbox site, and a login-wall fail-fast |
| Sentry | Tracing, Logs, AI agent monitoring, Profiling (backend) and Tracing + Session Replay (dashboard, project `mender-dashboard`), verified live; failed-recovery alert created |
| Model comparison | 8 Gemini models, 90 paid trials; default is now `gemini-3.5-flash-lite` (see below) |
| Cooldown field `cooldown_remaining_s` | In the contract, backend and dashboard (countdown) |

Test status at the last run: backend 138 tests (25 opt-in skipped; the browser and real-runner suites add 15 more when enabled), dashboard 55, runner 12, `ruff` clean.

The endpoint builds the shared response model, dumps it once, and validates that same JSON with both
the Pydantic model and the JSON Schema before returning it. All four contract fields are enabled
(`error`, `heal_records`, `agent_cost_usd`, `agent_duration_ms`). Failures are HTTP 200 with
`status="failed"`, `healed=false`, `data={}`, no `diff`. Cost and agent duration go only to the request that
ran the agent, only when every invocation reported them, and never to joined requests or cooldown hits.

## Read and trace

| Source | Responsibility and review focus |
| --- | --- |
| [main.py](main.py) | Startup validation, Sentry init, bounded fast-path lock, active-task joining, cooldown lookup, shielded waiting, each waiter's own replay, write guard, operator endpoints, response building |
| [recovery.py](recovery.py) | Application-owned tasks, one baseline, three-invocation loop, ordered progress, deadline, final canary, rollback, record finalization, cooldown cache, measurements |
| [healer.py](healer.py) | Lazy SDK imports, Gemini, executed-history grounding, live CSS capture, browser and Google client cleanup, per-run directory cleanup, agent span attributes |
| [runner.py](runner.py) | CLI subprocess, separate stdout/stderr, per-operation and deadline timeouts, process-group termination, raw output validation, owned artifacts. No selector locks |
| [store.py](store.py) | One store and lock per workflow, validated atomic writes, backups, higher-version restoration, the in-flight marker and its startup recovery |
| [config.py](config.py) | Loads definitions from `contracts/workflows/` (shared `WorkflowDefinition`), `selectors_for(workflow)`, settings, `write_allowed`, `prune_runs`, runner interpreter default |
| [reset.py](reset.py) | Restore from a backup or from git `HEAD` under the same lock |
| [terminal.py](terminal.py) | Rich rendering without emojis; original records and telemetry preserved |
| [sandbox/records_site.py](sandbox/records_site.py) | Local stateful site for write workflows (Chaos Mode, decoys with `hard`, `/state`, `/reset`) |
| [rehearse.py](rehearse.py), [rehearse_ui.py](rehearse_ui.py), [bench_models.py](bench_models.py) | Paid tools: API demo loops, real-browser dashboard loops, model comparison |
| [proposals/](proposals) | Changes proposed to other owners (not applied) and a paste-ready message for Person 1 |

## Recovery state and invariants

1. Startup loads workflows and schemas. The configured demo workflow, defaulting to the selector map's
   workflow ID, requires a canary. Missing runner or workflow configuration is an explicit 503. Invalid
   parameters return 422.
2. If a workflow has an active recovery, join it. Otherwise acquire the shared lock within five seconds,
   validate map compatibility, and run deterministic execution. Keep the lock for that execution, but bound
   only acquisition.
3. A runner failure needs valid, run-owned evidence before recovery, and must be at a selector step. A
   failure at a step that is not in the selector map (for example the page did not load) is reported as
   `runner_failed` and never starts a recovery. Register an application-owned task without an intervening
   await. Existing waiters share its result. A request cancellation must not cancel the task.
4. Recovery starts its 240-second clock at task creation, before exclusive-lock waiting. Work stops after 210
   seconds; 30 seconds remain for emergency cleanup and rollback. The initial fast run and any waiter's final
   replay are outside this recovery clock. Tests use shorter injected Settings values.
5. Under the exclusive lock, reread selectors and replay if another writer changed them. Then validate
   workflow, field, expected selector, and origin; save exactly one baseline backup before the first agent
   attempt.
6. Invoke Browser Use at most three times. Agent errors, timeouts, no-result and `agent_blocked` (the agent gave
   up, for example at a login or access wall) may retry the same field. Ambiguous evidence, invalid candidates,
   and cleanup failures are terminal. SDK-internal retries do not reset this cap. `agent_blocked` is retryable
   because models sometimes give up early on a normal page and a retry usually succeeds; a real login wall
   spends the cap and fails with no records.
7. Ground each candidate in one executed action, result and element match. CSS comes from stable attributes,
   a unique tag, or live structural targeting. An agent completion statement is never sufficient. No mutable
   class or XPath is stored.
8. Write each candidate atomically at the next version. Replay under the lock already held;
   `Runner.execute` must never reacquire it. Reads are ordered after the steps (a read field sits at position `len(steps) + index`). A valid later-step failure retains provisional progress;
   same or earlier failures abort. Three attempts exhausted also abort.
9. Final replay output must pass JSON Schema. Run a separate canary, validate raw output, then compare after
   explicit volatile-field exclusions. Commit only after all checks pass. Every definition requires a canary.
10. Any terminal failure restores the entire baseline if a patch was installed, as a new version greater than
    every provisional version. No installed patch means no restoration write. Rollback failure blocks service.
11. Successful waiters replay with their own parameters and run IDs; failed flights return the failure to
    existing waiters. After cleanup, a failed attempted recovery is stored for 15 s (`Recovery.cooldown`, set
    as the last synchronous step of `run()`). Lookup, join and registration in `main.py` have no await between
    them. The key uses the map on disk after cleanup (rollback bumps the version) and a failure fingerprint
    that ignores class attributes (the portal randomizes them). Hits never extend expiry. Uncacheable: config
    errors, cancellation, failed cleanup or restoration, and failures without valid evidence.
12. Records: one draft per candidate with a non-empty selector, in attempt order, finalized in `run()`'s
    `finally`: `committed`, `rolled_back` (shared `rollback_version`), or `rejected` (never written). Failed
    restoration drops them all.
13. Emit one measurement record per recovery. Independent background Sentry transactions retain the
    originating trace ID and can finish after the owner request closes.
14. A workflow with `mutates: true` runs only when the selector map's `target_url` host is loopback or in
    `MENDER_WRITE_HOSTS`, and is refused before the runner starts. The generic runner navigates to that same
    `target_url`, so the guard checks the page that is actually visited.
15. Operator endpoints (`/api/v1/admin/reset`, `/api/v1/status`) accept only loopback peers and refuse any
    request carrying forwarding headers. Reset takes `{workflow?}` (one or all), restores git `HEAD` selectors
    as a new version under that workflow's exclusive lock, refuses (409) only the workflow that is recovering,
    and clears only that workflow's cooldown.
16. Locks, stores and cooldown are per workflow; a recovery on one site never blocks another's fast path.
    `configuration_error` stays global. Startup validates every map against its definition (all step and
    output fields present) and blocks with a clear status otherwise.
17. Read healing (`healer.read_candidate`): the agent returns the visible values through `output_model_schema`;
    a JS probe finds the unique deepest element showing exactly them (no INPUT, TEXTAREA, SELECT or OPTION;
    case kept, whitespace collapsed); the selector comes from the shared `DERIVE` template, attributes first,
    never classes, and is rejected if it embeds a reported value; the replay must read back the reported values;
    then the canary decides. A field whose outputs are all attributes is refused before the agent runs.
18. Crash recovery: `mark_inflight` writes `state/inflight-<wf>.json` (pointing at the baseline) before the
    first write; `clear_inflight` runs after commit, rollback, or when nothing was installed. At startup, under
    the exclusive lock, a leftover marker restores its baseline as a new higher version, logs it and sends a
    Sentry event; a failed rollback keeps the marker, a marker without its backup blocks the backend. Plain
    `baseline-*.json` files are never auto-restored. `runs/` is pruned to the newest 50 at startup only.

All selector writers must follow the lock protocol, including reset. Outside editors do not participate.
Graceful shutdown drains active tasks. Client and proxy timeouts must cover at least 240 seconds plus initial
execution, waiter replay and network overhead. A timeout is not a reset request.

## SDK evidence and derivation

Verified runtime: Python 3.12.2 and browser-use 0.13.11. Gemini uses native `ChatGoogle`, with model and key
from the environment. The wrapper requires `max_retries >= 1`; the adapter uses 1, six steps, one action per
step, and one consecutive failure before stopping. Browser Use stays absent on fast success. The SDK counts
thinking tokens as output tokens and prices them with its pricing table, so its cost estimates include them.

The recorded history fixture projects a real Browser Use and Chrome run driven by scripted model responses. It
establishes SDK history shape, not model reasoning. Candidate order is `data-testid`, `data-test`,
`data-action`, `data-field`, `id`, `name`, `aria-label`, a unique tag, then ancestor, direct-child and
`:nth-of-type()` structure. Every candidate is checked against the exact live node before capture. Classes
are ignored. Structural CSS may break if the page is reordered later. Missing or unsupported targets fail
explicitly and cannot authorize a write.

Emergency browser cleanup depends on the pinned SDK's private local-browser watchdog PID; only its owned
process tree is targeted, so review it on SDK upgrades. ChatGoogle caches a Google client that is closed
(async and sync) after every invocation. Each invocation's browser profile and file-system directories under
`state/` are deleted afterwards.

## Tests and evidence

Commands are in [README.md](README.md#tests-and-tools). The default suite makes no model calls. Key tests:
[test_m2.py](tests/test_m2.py) (ordered two-field repair without a re-entrant deadlock; canary failure restores
both patches as 1, 2, 3 then 4; later-repair failure; deadline during the agent; request cancellation keeps the
shared recovery), [test_m3.py](tests/test_m3.py) (cooldown, reset, records, measurement ownership, waiters,
sanitized messages, schema validation, review fixes), [test_writes.py](tests/test_writes.py) (write guard and
sandbox site), [test_real_runner.py](tests/test_real_runner.py) (real runner and portal),
[test_selectors.py](tests/test_selectors.py) (real DOM derivation), [test_m1.py](tests/test_m1.py) (regression
coverage for artifacts, cleanup, rollback failure, atomic writes, tracing, reset and the import boundary).
New on this branch: [test_workflows.py](tests/test_workflows.py) (two workflows in one backend: routing, lock
isolation, per-workflow cooldown and reset, 409 only for the recovering workflow, startup consistency),
[test_read_heal.py](tests/test_read_heal.py) (read healing rules), [test_crash_recovery.py](tests/test_crash_recovery.py)
(marker lifecycle, startup restore, failed-rollback retention, pruning), and the runner's `test_execute.py`.
Mutations proven caught by a named test: lock isolation, reset clearing every cooldown, reset 409 scope, read
positions, a value embedded in a selector, the unique-element requirement, the attribute-only refusal, the
replay-versus-reported check, canary-only acceptance, marker lifecycle, startup recovery and pruning.

Adversarial mutations (isolated process, source untouched), each caught by a named test: no-op cooldown,
expiry extended on hits, a key ignoring the failed step, a key ignoring the selector map, a key that includes
class attributes, rolled-back records labelled committed, restoration replaced by a no-op, ordered-step
positions forced to zero, the write guard removed, the navigation guard removed, the forwarded-header check
removed, directory cleanup removed, and the explicit Sentry capture removed.

### Measured runs

Gemini `gemini-3.8-flash` (the default before the model comparison; see "Choosing a Gemini model"), local Chrome, SDK cost estimates (not billing receipts), single
samples (not percentiles):

| Run | Request | Agent invocations | Tokens (prompt / completion) | SDK cost | Notes |
| --- | --- | --- | --- | --- | --- |
| Fixture, one broken button | 23.9 s | 1 | 21,820 / 1,487 | $0.0219 | records committed 1 to 2 |
| Fixture, two broken fields | 43.0 s | 2 | 43,616 / 2,986 | $0.0439 | records 1 to 2 to 3 |
| Real portal and runner, Chaos Mode, API loops | 21.5 to 40.3 s over 13 loops | 1 | about 29.7k / 2.2k to 2.5k | $0.028 to $0.032 | fast path 366 to 379 ms over HTTP (538 ms once, a cold first request); every record committed |
| Sandbox site, save button | 28.9 s | 1 | n/a | $0.031 | exactly 3 writes: agent, replay, canary |
| Dashboard, real browser, 3 loops | 29.9 to 32.4 s | 1 | n/a | about $0.031 | `rehearse_ui.py`, 3 of 3 pass |

`python -m services.backend.rehearse 5` passed 5 of 5 loops, twice (before and after the canary change). The
400 ms target is not proven: fixture and local-portal numbers do not describe a real site's latency.

## Integration with the other services

`origin/phase-1` (portal and runner) and `origin/mender-dashboard` are merged. Cross-owner edits were made at
the backend owner's request, each in its own commit so it can be reviewed or reverted on its own. Earlier (PR #1):

1. **Runner** `services/runner/execute.py`: accepts the agreed `--workflow --params --run-id` (plus
   `--sentry-trace`, `--baggage`) and writes `runs/<run_id>/failure_payload.json` and `failure.png`; the old flags
   still work. It returns `permit_id` (the portal echoes the submitted id) so the canary can tell a wrong repair.
2. **Contracts**: `target_url` is the real portal address (was `portal.example.gov`, which made the backend
   reject every failure as `unexpected_page`).
3. **Runner** `reset_demo.py`: resets through the backend's locked endpoint when one is listening; edits the file
   itself only when the connection is refused (a timeout or reset from a live backend is an error, not a bypass).
4. **Dashboard**: sends the backend's request contract `{workflow, params}` (it sent `{workflow_id}` and got 422);
   failed runs are labeled by what happened (reverted only if a rolled-back record exists, "no selector changed"
   otherwise, "rollback failed" when so); request errors are shown instead of "Idle"; the previous run's banner and
   label are hidden while a new run is in flight; rejected records are "never installed"; trace links use
   `/explore/traces/trace/`; a Reset selectors button (live mode) calls the admin endpoint and reports a blocked backend.

On this branch (also separate commits): the **generic runner** (`execute.py` runs any definition and opens the
map's `target_url`, so the old permit-only code and the test shims `real_runner_shim.py` and `sandbox_runner.py` are
gone), the **contracts layout** (definitions in `contracts/workflows/`, one map per workflow in
`contracts/selectors/`, `WorkflowDefinition`/`WorkflowSummary`, `cooldown_remaining_s`), and the **dashboard**
(workflow picker, per-workflow reset, "n/a" instead of fixture numbers in live mode, cooldown countdown, Sentry
tracing and Session Replay). Tests build their roots with `tests/support.py::make_root`, which copies only the
schemas and one workflow's definition and map. Full-stack proof: real portal, real runner, backend under uvicorn,
real Gemini, real dashboard in Playwright, repeated loops; one backend served `permit-application` (heal 13.9 s,
$0.0067) and `record-update` (fast 419 ms, heal 16 s, $0.0056) with independent resets.

## Write workflows (local sites only)

Reads work on any reachable site; writes only on sites we control, because public sites cannot be modified.
`Workflow.mutates` plus `config.write_allowed` enforce it before the runner starts (lookalike hosts such as
`127.0.0.1.evil.com` and `user@host` URLs are refused). A real-browser chaos heal on the sandbox site (mocked
agent) wrote exactly twice (replay and canary); a paid run wrote three times (agent, replay, canary), which is
why writes need an idempotent action and a repeat-safe canary. A login or access wall ends as `agent_blocked`
after the three-invocation cap. Public sites may block headless browsers; that is untested. Read healing was proven live: with the saved value's
test id renamed, a paid heal took 17.6 s and $0.0065 and produced `span[data-testid="result-value"]` as an
`action_type: read` record.

## Sentry

Projects `mender-backend` and `mender-dashboard`, org `tanish-misra`. The DSNs are only in git-ignored files
(`services/backend/.env`, `services/dashboard/.env.local`). The run guide describes what each product sends;
this is what was verified by querying the projects, and what it changed in the build:

- **Tracing, distributed.** One dashboard click is one trace: `ui.action.click` and the browser fetch,
  `http.server` > `workflow.execute` > `healer.recovery` > `healer.diagnose` > `gen_ai.invoke_agent` > four
  `gen_ai.chat` > `http.client`, then `healer.patch` > `runner.execute` replays. Browser and backend spans share
  one trace id. The click span and the fetch span are siblings under the pageload, not parent and child.
- **AI agent monitoring.** `invoke_agent Browser Use` carries agent name, model and token counts (`gen_ai.*`).
  The spans showed about four sequential model calls of about 5 s each, which led to the model comparison
  below: the default model heals in about 11 s for about half a cent, 6x cheaper and 2.2x faster than before.
- **Profiling.** `profile_lifecycle="trace"` with a sample rate of 1.0; backend spans carry `profiler.id`.
- **Logs.** Backend logs are sent as Sentry Logs next to the spans (a heal trace had 36).
- **Session Replay** (dashboard, `VITE_SENTRY_REPLAY_RATE`, 0.1 by default, 1 while demoing, always on error).
  A replay is linked to the backend issue `MENDER-BACKEND-1` through the shared trace.
- **Runner phase timings** (`runner.<phase>_ms` span data from the runner's stderr) showed that the fast path
  takes about 367 ms end to end but only about 151 ms is runner work (launch 83, goto 6, steps 52, reads 9);
  importing Playwright and starting and stopping its driver alone costs about 197 ms. The next optimization is
  a warm, long-lived driver. It is not built.
- **Summary span.** `healer.summary` carries flat `recovery.cost_usd`, `recovery.agent_duration_ms`,
  `recovery.total_tokens` (reliable values only), `recovery.invocations` and `recovery.success`. They are on a
  child span because Sentry did not expose attributes set on the transaction's root span. Custom attributes are
  queried as `tags[name,number]`. `cost_usd` (0.03084075, identical to the response), `agent_duration_ms` and
  `invocations` query correctly; `total_tokens` and `success` never became queryable (cause not found), so token
  charts use `gen_ai.usage.*`.
- **Issues and noise.** One failed recovery used to open six issues because every ERROR log line became one.
  With `LoggingIntegration(event_level=None)` only our fingerprinted events become issues; the `log.exception`
  sites capture explicitly. Verified: a new failed recovery added one event to our issue.
- **Alert.** "Mender: agent recovery failed" (id 6187285) emails the team when a new or reappearing issue has
  tag `tier:agent`. Chaos Mode's runner failure is `tier:deterministic` and does not fire it.
- **Dashboard.** The plugin cannot create dashboards; build it in the UI from the queries in the run guide.
- No dropped events. Ingestion lags a minute or two.

## Choosing a Gemini model

Decision: the default `GEMINI_MODEL` is now `gemini-3.5-flash-lite` (it was `gemini-3.8-flash`). Measured with
[bench_models.py](bench_models.py): 90 paid trials across 8 callable models (about $2.18 estimated), each a full
backend request with real Gemini, real Playwright replay, and the real canary, plus a second request that must succeed
on the healed selector. Cost is the Browser Use SDK's pricing table, which counts thinking tokens as output; it is an
estimate, not a bill.

Scenarios: **permit** (the demo; Chaos Mode breaks the submit button) and **sandbox-hard** (the local record editor with
Chaos Mode plus a decoy search box and "Save draft" and "Clear form" buttons; a trial also requires the write to land on the
site). A trial passes only if the heal committed, the next request succeeded, and the output was correct.

Summary under the shipped policy (an agent that gives up early is retried within the cap):

| Model | Permit demo | Time | Cost per heal | Hard sandbox | Time | Cost per heal |
| --- | --- | --- | --- | --- | --- | --- |
| `gemini-3.5-flash-lite` (default) | 5/5 | 11.4 s | $0.0052 | 5/5 | 12.3 s | $0.0054 |
| `gemini-3.1-flash-lite` | 5/5 | 15.4 s | $0.0055 | 5/5 | 18.2 s | $0.0060 |
| `gemini-3-flash-preview` | 5/5 | 24.1 s | $0.0131 | 5/5 | 23.5 s | $0.0139 |
| `gemini-3.6-flash` | 5/5 | 22.0 s | $0.0164 | 5/5 | 27.0 s | $0.0201 |
| `gemini-3.7-flash` | 5/5 | 25.2 s | $0.0297 | 5/5 | 27.1 s | $0.0320 |
| `gemini-3.8-flash` (previous default) | 5/5 | 24.8 s | $0.0307 | 5/5 | 26.4 s | $0.0307 |
| `gemini-3.5-flash` | 5/5 | 22.4 s | $0.0361 | 5/5 | 26.0 s | $0.0418 |
| `gemini-3.1-pro-preview` | 5/5 | 54.8 s | $0.0484 | 5/5 | 45.0 s | $0.0373 |

All trials:

| Model | Scenario | Success | Mean time | Mean cost | Cost per success | Agent invocations | Failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gemini-3.5-flash-lite` | permit, give-up terminal (before the retry fix) | 5/5 | 11.4 s | $0.0052 | $0.0052 | 1.0 | none |
| `gemini-3.5-flash-lite` | hard sandbox | 5/5 | 12.3 s | $0.0054 | $0.0054 | 1.0 | none |
| `gemini-3.1-flash-lite` | permit, give-up terminal (before the retry fix) | 5/5 | 15.4 s | $0.0055 | $0.0055 | 1.0 | none |
| `gemini-3.1-flash-lite` | hard sandbox | 5/5 | 18.2 s | $0.0060 | $0.0060 | 1.0 | none |
| `gemini-3-flash-preview` | permit, give-up terminal (before the retry fix) | 5/5 | 24.1 s | $0.0131 | $0.0131 | 1.0 | none |
| `gemini-3-flash-preview` | hard sandbox | 5/5 | 23.5 s | $0.0139 | $0.0139 | 1.0 | none |
| `gemini-3.6-flash` | permit, give-up terminal (before the retry fix) | 5/5 | 22.0 s | $0.0164 | $0.0164 | 1.0 | none |
| `gemini-3.6-flash` | hard sandbox | 5/5 | 27.0 s | $0.0201 | $0.0201 | 1.0 | none |
| `gemini-3.7-flash` | permit, give-up terminal (before the retry fix) | 5/5 | 25.2 s | $0.0297 | $0.0297 | 1.0 | none |
| `gemini-3.7-flash` | hard sandbox | 5/5 | 27.1 s | $0.0320 | $0.0320 | 1.0 | none |
| `gemini-3.8-flash` | permit, give-up terminal (before the retry fix) | 4/5 | 22.8 s | $0.0276 | $0.0345 | 1.0 | agent_blocked |
| `gemini-3.8-flash` | permit, retry fix | 5/5 | 24.8 s | $0.0307 | $0.0307 | 1.0 | none |
| `gemini-3.8-flash` | hard sandbox | 5/5 | 26.4 s | $0.0307 | $0.0307 | 1.0 | none |
| `gemini-3.5-flash` | permit, give-up terminal (before the retry fix) | 5/5 | 22.4 s | $0.0361 | $0.0361 | 1.0 | none |
| `gemini-3.5-flash` | hard sandbox | 5/5 | 26.0 s | $0.0418 | $0.0418 | 1.0 | none |
| `gemini-3.1-pro-preview` | permit, give-up terminal (before the retry fix) | 3/5 | 53.2 s | $0.0372 | $0.0620 | 1.0 | agent_blocked |
| `gemini-3.1-pro-preview` | permit, retry fix | 5/5 | 54.8 s | $0.0484 | $0.0484 | 1.4 | none |
| `gemini-3.1-pro-preview` | hard sandbox | 5/5 | 45.0 s | $0.0373 | $0.0373 | 1.0 | none |

Findings:

- Accuracy saturated: with the retry policy every model is 5/5 on both tasks, and none picked a decoy. The models differ
  in cost and speed, so the cheapest fast model wins. `gemini-3.5-flash-lite` heals in about 11 s for $0.0052, which is
  6x cheaper and 2.2x faster than `gemini-3.8-flash` on the same task. A confirmation through the dashboard (2 loops, real
  UI, default model from `.env`) healed in 12.8 s and 11.8 s at $0.0065 and $0.0050.
- The benchmark exposed a real flaw in our own change: `agent_blocked` (the agent declared failure) was terminal, so
  `gemini-3.8-flash` (1 of 5) and `gemini-3.1-pro-preview` (2 of 5) failed normal heals by quitting early. It is now retryable,
  which restored both to 5/5; the pro model then averaged 1.4 invocations (55 s, $0.0484 per heal).
- Selectors were always attribute based (`button[data-action="submit"]` or `...="save"`), never structural.
- Limits: 5 trials per model per scenario, one site family, SDK cost estimates, preview models that may be renamed or
  repriced, and the 2.5 family is no longer available to this key. Treat close results (for example the two flash-lite
  models) as ties. The raw results are in [benchmarks/model-comparison-2026-10-17.json](benchmarks/model-comparison-2026-10-17.json).

## Code review

An independent review of the whole branch produced 15 findings. Triaged against the code, 13 were fixed with a
test that fails without the fix, 1 was fixed in part, and 1 is documented:

- Fixed (backend): a navigation-step runner failure started a pointless recovery with a misleading error; the
  runner interpreter default had no Playwright; `log.exception` sites stopped reaching Sentry; per-run browser profile directories were never deleted;
  `rehearse.py` crashed on an omitted record list and ran paid loops on import; `bench_models.py` undercounted its
  spend cap; `rehearse_ui.py` could pass on stale text.
- Fixed (runner, dashboard): `reset_demo.py` bypassed the backend on a timeout; request errors were invisible;
  stale banner and agent label during a new run; rejected records labeled "restored"; reset hid a blocked backend;
  a quick tab switch left a panel invisible.
- Partly fixed: the operator endpoints no longer accept a test-only host and refuse forwarded requests, but the
  "loopback only" check is still satisfied by the Vite dev proxy. Do not run the dev server with `--host` or a
  tunnel while the backend is live.
- Since fixed: the runner now navigates to the selector map's `target_url`, so the write guard checks the page that
  is actually visited.

## Open items and limits

- **Warm driver.** Playwright import and driver start cost about 197 ms of the 367 ms fast path. A persistent
  driver is the measured next optimization; not built.
- **Public sites.** Tried on five real sites (read-only workflows with a search or click step, scratch roots, not
  committed): python.org, Wikipedia, scrapethissite.com, the-internet.herokuapp.com, httpbin.org. Fast path: python.org
  (0.5 s), scrapethissite (1.0 s), Wikipedia (0.9 s) and httpbin (0.8 s) ran first time with correct output. With the
  submit button's selector broken on purpose, a paid heal worked on python.org (`button[id="submit"]`, 13 s, $0.0046)
  and Wikipedia (`form[id="searchform"] > div > button`, 16 s, $0.0075), and the next request ran on the new selector.
  Findings: (1) a step's `label` and `role` must equal the page's accessible name and role exactly (`Search for
  Teams:` with the colon; Wikipedia's box is a `searchbox`), or grounding refuses with `ambiguous_element`; (2) if
  the agent shortcuts the task without clicking (scrapethissite once navigated to `?q=...` directly), there is no
  click evidence, so the heal is refused and rolled back, which is safe but not a repair; (3) the 2 s per-step cap
  also bounds page load and reads, so a result that appears after about 5 s (the-internet dynamic loading) fails
  the fast path; (4) an output that echoes volatile data (httpbin's headers include a trace id) cannot have a
  canary, so the heal was rolled back as `canary_failed`. Login or captcha walls and sites that block headless
  browsers were not tried. Total spend about $0.05.
- **Read healing limits.** It needs a visible `text` output on the field (attribute-only outputs refuse). When
  every output of a field is constant across params, only uniqueness, the intersection rule and the canary
  protect against a wrong element.
- **Contract decisions.** The team owns the contracts together. Recorded: `agent_duration_ms` is the sum of SDK
  step durations, and empty `heal_records` are omitted (equivalent to `[]`).
- **Sentry.** No dashboard was created (the plugin cannot); `recovery.total_tokens` and `recovery.success` are not
  queryable. In the trace tree the click span and the fetch span are siblings.
- **Backend.** Synchronous filesystem work cannot be preempted, so the 240 s ceiling is not a guarantee against an
  OS stall. POSIX locks and process groups, one uvicorn worker, and an in-memory cooldown are demo constraints.
  `configuration_error` is global, not per workflow. Subprocess output is buffered in memory with no size
  limit and there is no load testing. Iframes and dynamic or duplicate labels may fail grounding.
- **Cooldown fingerprint.** A site whose failure DOM snippet contains dynamic content (a token or a clock) makes
  every failure look new, so the cooldown never hits. Safe, but it defeats the feature.
- **Dashboard.** History is in memory, so the first real heal replaces the "n/a" cards only for that session.
  Reset is a button, but Chaos Mode is still turned off on the portal.

If restoration or cleanup fails, inspect the logged reason, preserve the baseline, stop owned resources, reset
under the same lock, and restart before retrying (a restart alone also retries it through the in-flight marker).
