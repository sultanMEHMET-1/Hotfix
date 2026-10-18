# Backend (`services/backend`)

The backend turns the deterministic runner into a JSON endpoint that repairs itself. It runs a
workflow through the runner, and when the site has changed it asks a Browser Use agent (Gemini)
to complete the workflow, derives a CSS selector for the broken field from the agent's recorded
history, proves it by replaying the runner, and only then commits the new selector. Recovery is
transactional: a repair is kept only if the full replay, the output schema, and a canary all pass,
otherwise the original selectors are restored. M1 (single field), M2 (multi-field transaction)
and M3 (failure cooldown, finalized `heal_records`, reset) are shipped and merged into `main`.

Related docs: [root README](../../README.md) (whole-stack quick start), [AGENTS.md](AGENTS.md)
(rules for agents working here), [CLAUDE.md](CLAUDE.md) (project brief), [HANDOFF.md](HANDOFF.md)
(code map, invariants, evidence, open items), [contracts](../../contracts/README.md).

## Run

From the repository root, with Python 3.12 and `uv`. The runner needs Playwright, which lives in
the project venv created by `services/runner/setup_venv.sh`, so point the backend at that
interpreter for its runner subprocess:

```sh
MENDER_RUNNER_PYTHON="$PWD/.venv/bin/python" \
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements.txt \
  python -m uvicorn services.backend.main:app --env-file services/backend/.env \
  --host 127.0.0.1 --port 8000 --workers 1
```

Use one worker and bind to loopback. The local `.env` is git-ignored; start from `.env.example`
and set `GOOGLE_API_KEY`, `GEMINI_MODEL`, and optionally `SENTRY_DSN`. Missing model
configuration only affects recovery. The deterministic success path imports neither the healer
nor Browser Use, and Browser Use imports run in a thread after a runner failure so its cold import
does not block the event loop. Without a DSN everything runs locally.

### Endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/run-workflow` | `{"workflow": "<id>", "params": {...}}`. Returns the shared `WorkflowExecutionResponse` |
| `POST /api/v1/admin/reset` | Loopback only. Restore the committed selectors as a new version and clear the cooldown; 409 during a recovery |
| `GET /api/v1/status` | Loopback only. Why the backend is blocked (if it is), active recoveries, cooldown seconds left |

Valid execution attempts return HTTP 200, with failure represented by `status="failed"`,
`healed=false`, `data={}`, a structured `error`, and no `diff`. `error.message` is safe to show
(no keys, paths, prompts or stack traces; detail stays in logs and Sentry). `heal_records` lists
every candidate that reached the page, in attempt order, and is omitted when empty.
`agent_cost_usd` and `agent_duration_ms` appear only on the request that ran the agent, only when
every invocation reported them, and never as 0 for unknown. The response is validated against both
the Pydantic model and the JSON Schema before it is returned. Invalid input returns 422, unknown
workflows 404, and missing workflow or runner configuration 503.

## Settings

| Variable | Default |
| --- | --- |
| `GOOGLE_API_KEY`, `GEMINI_MODEL` | Required for recovery; the model name is never hard-coded |
| `SENTRY_DSN` | Empty: Sentry is off |
| `MENDER_WORKFLOWS_DIR` | `contracts/workflows/` if it exists, otherwise backend `workflows/` |
| `MENDER_RUNNER_SCRIPT` | Repository `services/runner/execute.py` |
| `MENDER_RUNNER_PYTHON` | The backend's own interpreter. Set it to `.venv/bin/python` so the runner has Playwright |
| `MENDER_RUNNER_TIMEOUT` | 45 seconds per subprocess |
| `MENDER_AGENT_TIMEOUT` | 90 seconds, clamped to the shared remaining recovery budget |
| `MENDER_DEMO_WORKFLOW` | Selector map workflow ID; its definition must include a canary |
| `MENDER_HEADLESS` | `true`; set `false` to display the agent browser |
| `MENDER_BROWSER_EXECUTABLE` | Browser Use's local browser discovery |
| `MENDER_WRITE_HOSTS` | Empty. Extra hostnames (comma separated) where `"mutates": true` workflows may run, besides loopback |
| `MENDER_PROPAGATE_TRACE` | `false`; enable only when the runner supports the optional trace flags |
| `MENDER_LOG_LEVEL` | `INFO`; `DEBUG` for detailed SDK console output |

The runner is called as `--workflow <id> --params '<json>' --run-id <uuid>` (plus optional
`--sentry-trace` and `--baggage`) with the repository root as its working directory, without a
shell, and with its own UUID per subprocess. Only artifacts at `runs/<run_id>/` are used. The runner
should use roughly a two-second per-step timeout so broken selectors reach healing promptly. A
runner timeout without failure evidence does not start a blind browser repair.

## Workflow definition

Create `<workflow_id>.json` in the workflows folder. `goal` is top-level, `steps` are the
authoritative execution order, and `fields` in the selector map is only a lookup. The demo
definition is `workflows/permit-application.json`.

```json
{
  "goal": "Look up the record using record_id and return its status.",
  "steps": [
    {"field": "input_reference", "action_type": "input", "role": "textbox", "label": "Record reference"},
    {"field": "submit_button", "action_type": "click", "role": "button", "label": "Look up record"}
  ],
  "params_schema": {
    "type": "object", "required": ["record_id"], "additionalProperties": false,
    "properties": {"record_id": {"type": "string"}}
  },
  "output_schema": {
    "type": "object", "required": ["record_id", "status"], "additionalProperties": false,
    "properties": {"record_id": {"type": "string"}, "status": {"type": "string"}}
  },
  "canary": {
    "params": {"record_id": "known-record"},
    "expected_output": {"record_id": "known-record", "status": "found"},
    "ignore_paths": []
  },
  "mutates": false
}
```

Every step field must exist in the current selector map. Matching uses executed actions and
results, action type, ordered workflow position, and a unique role and label. If `label` is
omitted, a unique label must be available in the failure DOM snippet. Missing or ambiguous
evidence fails explicitly. CSS is checked against the live element before use; the agent's
success text is never verification. Reading a result element back, and iframes, are unsupported.

Canary exclusions are explicit JSON Pointer paths to object fields, such as `/updated_at`. Raw
output must pass its schema before masking. Missing exclusion paths, root exclusions, array
indexing, and masking all meaningful values are rejected. A canary is required for the demo
workflow; other definitions may omit one, which limits verification to replay and schema checks.
A canary should be able to tell a correct repair from a wrong one (the permit portal echoes the
submitted permit id for exactly that reason).

## Recovery behavior

Reset, rollback, and execution use the same file lock. One exclusive lock covers the baseline
backup, diagnosis, provisional patches, replay, canary, and rollback; replay and canary never
reacquire it. A later ordered failed step permits another attempt, and a same or earlier failed
step aborts. Agent errors, timeouts, and no-result outcomes may retry the same field within the
three-invocation cap. Ambiguous history or an invalid candidate aborts immediately. An agent that gives up (`agent_blocked`,
for example at a login or access wall) is retried too, since models sometimes quit early on a normal page. All installed patches roll back together on terminal
failure, as a version higher than every provisional version; no installed candidate means no
restoration write.

The application keeps one active background recovery task per workflow. Requests join through a
shield, so disconnecting or cancelling one request does not stop healing. Successful waiters
replay using their own parameters and run IDs, and failure returns the same outcome to existing
waiters. Graceful shutdown waits for active recoveries.

Recovery has one 240-second monotonic budget, starting before exclusive-lock waiting. Work stops
at 210 seconds, reserving 30 seconds for emergency browser/process cleanup and rollback. Per-agent
and per-runner timeouts cannot extend the deadline. Ordinary fast-path lock acquisition is bounded
to five seconds; requests join a known active recovery instead of failing that wait.

**Clients and proxies must allow at least 240 seconds plus initial runner time, any waiter replay,
and network overhead.** A client timeout does not undo or cancel a repair. The initial deterministic
run is outside the recovery budget. Forced termination, process crashes, and blocked OS or
filesystem operations are outside this application-level deadline guarantee.

## Failure cooldown and heal records

After cleanup finishes, one failed recovery per workflow is kept in memory for 15 s
(`failure_cooldown`, event loop monotonic clock). A later runner failure that matches on workflow,
failed step, old selector, the whole selector map (taken after cleanup, so a rollback's higher
version is included), and a hash of the failure artifact's page URL, DOM snippet and error message
gets the original error and records back, with no agent, no writes, and no new measurement file.
Class attributes are ignored in the DOM snippet, because the portal randomizes them on every load.
Any other difference starts a fresh recovery. Hits never extend expiry, a restart clears the cache,
and a `COOLDOWN` log line names the originating recovery and time left. Configuration errors,
failures without valid runner evidence, cancellations, and failed cleanup or restoration are never
cached. Deterministic execution continues during cooldown.

Each record is `committed` (final replay, schema and canary passed), `rolled_back` (installed, then
the transaction failed and the baseline was restored; all share one `rollback_version`), or
`rejected` (a grounded candidate refused before it was written, with no `version_after`). Agent
errors, empty results, and ambiguous evidence stay log and Sentry events, never records. Records
describe the selector transaction; `status` describes the caller's own run, so a waiter whose replay
fails after a shared heal keeps the committed records, its own error, and no `diff`. If baseline
restoration fails, records are omitted, `error.code` is `rollback_failed`, and the backend blocks
execution (HTTP 503) until restored and restarted.

## Selector derivation

Candidates are tried in this order: `data-testid`, `data-test`, `data-action`, `data-field`, then
`id`, `name`, `aria-label`, a unique tag, and structural CSS. Structural fallback walks the live DOM,
using ancestor attributes, direct-child combinators, and `:nth-of-type()` where needed. Classes are
not used. Each candidate must select exactly one element and that element must be the agent's
interacted node. XPath identifies the live node but is never stored as CSS. Structural selectors
may break on later reordering. Missing, detached, iframe, or otherwise unresolved targets fail
explicitly and restore all provisional changes. There is no blind first-match fallback.

## Read and write workflows

Reading works against any site the runner can reach. A workflow that changes data sets
`"mutates": true`. The backend refuses it (`error.code` `write_not_allowed`, no runner started)
unless the selector map's `target_url` host is loopback or listed in `MENDER_WRITE_HOSTS`, and the
agent prompt then asks for the update exactly once instead of "do not modify data". Expect repeated
writes during a heal: the agent's own run, the replay, and the canary each save once, so write
workflows need an idempotent action (set a value, then read it back) and a repeat-safe canary.

Public sites that need a login or show a captcha are not bypassed. The agent is told to stop and
report failure, which becomes `agent_blocked` (retried within the cap, then a failure with no records); a runner that cannot find its selector
behind such a wall fails and rolls back the same way.

`sandbox/records_site.py` is a local stateful site for write demos
(`python services/backend/sandbox/records_site.py --port 3100`). Chaos Mode breaks its save button,
`GET /state` shows stored records and the write count, and `POST /reset` clears it.

## Operator commands

Loopback callers only:

```sh
curl -X POST localhost:8000/api/v1/admin/reset   # restore committed selectors, clear cooldown
curl localhost:8000/api/v1/status                # blocked reason, active recoveries, cooldown left
```

Reset restores `contracts/selectors.json` from git `HEAD` as a new higher version, so do not commit
a healed selector map. With the server stopped, `python -m services.backend.reset --original` does
the file part. Reset does not turn Chaos Mode off; that is a click on the portal. After
`rollback_failed` the backup path is in the ERROR log: run
`python -m services.backend.reset services/backend/state/baseline-<run_id>.json` and restart. Do not
put a proxy in front of uvicorn that forwards the admin or status paths; they trust the peer address.

## Sentry

Project `mender-backend` (org `tanish-misra`). Traces are sampled at 100 percent and logs are sent
as Sentry Logs. One request is one trace: `http.server` > `workflow.execute` > `healer.recovery` >
`healer.diagnose` > `gen_ai.invoke_agent` > `gen_ai.chat` (the Google client is instrumented by the
SDK) with `http.client` children, then `healer.patch` > `runner.execute` replays.

- **Issues.** Only our own events become issues, with stable fingerprints:
  `["mender.runner", workflow, failed_step, expected_selector]` for a runner failure and
  `["mender.recovery", workflow, error code, failed_step, expected_selector]` for a failed recovery.
  `LoggingIntegration(event_level=None)` keeps ERROR log lines as logs, not issues (otherwise one
  failed recovery opened six). Tags: `workflow`, `mode`, `tier` (`deterministic` or `agent`),
  `old_selector`, `new_selector`, `heal_success`. Contexts: `runner.failure`, `recovery.measurements`.
- **Agent span.** `invoke_agent Browser Use` carries `gen_ai.agent.name`, `gen_ai.request.model`,
  and `gen_ai.usage.input_tokens` / `output_tokens`, so AI Agent Monitoring can chart it.
- **Summary span.** A small `healer.summary` child span of the recovery carries flat numbers `recovery.cost_usd`,
  `recovery.agent_duration_ms`, `recovery.total_tokens` (only when every invocation reported them),
  `recovery.invocations` and `recovery.success`, for dashboards. They are on a child span because Sentry
  indexes child span data for queries but not a transaction's own root span.
- **Alert.** "Mender: agent recovery failed" emails the team when a new or reappearing issue has
  tag `tier:agent`. The expected runner failure that Chaos Mode causes is `tier:deterministic`, so a
  normal demo does not page anyone.
- **Dashboard.** Sentry's plugin cannot create dashboards, so build one in the UI (Dashboards, Create,
  Add Widget, dataset Spans): `span.op:healer.recovery` charted as `p50(span.duration)` and
  `p95(span.duration)` for heal latency; `span.op:healer.summary` with `avg(tags[recovery.cost_usd,number])` for cost per heal
  and, for tokens, `span.op:gen_ai.invoke_agent` with `avg(gen_ai.usage.input_tokens)` and
  `avg(gen_ai.usage.output_tokens)` (custom attributes are addressed as `tags[name,number]` in queries); and an Issues widget with query `tier:agent` for failures.
- Ingestion lags a minute or two, so counts queried right after a run look low.

## Terminal output

The backend uses Rich for a timestamped, color-aware console timeline:

```text
FAST       Running workflow permit-application
BROKEN     Runner exited with a failure
AGENT      Browser Use engaged for submit_button
AGENT      Step 1:
AGENT      Typed the requested record reference
PATCH      #submit-btn -> button[data-action="submit"] (version 2)
VERIFY     Deterministic replay and output schema passed
CANARY     Known lookup matched expected output
HEALED     Recovery verified
```

Rollback appears as its own `ROLLBACK` event and a cooldown hit as `COOLDOWN`. Emoji and SDK-supplied
ANSI escapes are removed in console rendering only; selectors and bracketed text stay literal, and
original log records, file handlers, Sentry context, and response data are preserved. Logs write to
stderr so they do not contaminate a JSON stdout stream. `MENDER_LOG_LEVEL=DEBUG` adds the detailed SDK messages.

## Tests and tools

Default suite (no model calls, no browser; opt-in tests skip):

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-test.txt \
  python -B -m unittest discover -s services/backend/tests -v
```

| What | Flag and command | Cost |
| --- | --- | --- |
| Real DOM selector derivation and the sandbox site | `MENDER_BROWSER_TEST=1` plus `-m unittest services.backend.tests.test_selectors services.backend.tests.test_writes`, live requirements, Chrome | free |
| Real runner and portal, mocked agent | `MENDER_REAL_RUNNER=1`, `-m unittest services.backend.tests.test_real_runner`, after `services/runner/setup_venv.sh` | free |
| Gemini heals (fixture, real portal, sandbox) | add `MENDER_LIVE_TEST=1` to the commands above, or `-m unittest services.backend.tests.test_live` | about $0.02 to $0.04 each |
| API demo loops | `python -m services.backend.rehearse 5` (portal on :3000, backend on :8000) | about $0.03 per loop |
| Dashboard demo loops in a real browser | `PLAYWRIGHT_BROWSERS_PATH=.venv/playwright-browsers .venv/bin/python services/backend/rehearse_ui.py 3` (dashboard on :5173 with mocks off) | about $0.03 per loop |
| Model comparison | `MENDER_REAL_RUNNER=1 ... -m services.backend.bench_models --models a,b --trials 5` | see below |

The live commands use `requirements-live.txt` (for example
`MENDER_LIVE_TEST=1 uv run --no-project --python 3.12 --with-requirements services/backend/requirements-live.txt
python -B -m unittest services.backend.tests.test_live -v`). On macOS the tests discover Google
Chrome; elsewhere set `MENDER_BROWSER_EXECUTABLE`. Test selectors, portals, screenshots and backups
live in temporary directories; product backups are `state/baseline-<run_id>.json`.

The recorded history fixture is a projection of a real Chrome and Browser Use 0.13.11 run driven by
scripted model responses. It establishes SDK history shape, not model reasoning.

## Measurements

Every recovery retains `state/recovery-<id>.json` (git-ignored) and logs the same numbers once:
request and recovery wall time, per-invocation wall time, SDK token usage (cached tokens are a
subset of prompt tokens), and SDK cost. Joined requests and cache hits do not duplicate usage. Unknown
usage or cost is omitted, with completeness flags for partial totals. The SDK's cost is an estimate from
its pricing table (including thinking tokens, which it counts as output), not a billing receipt, and SDK
step duration is never substituted for measured wall time. Measured runs are in [HANDOFF.md](HANDOFF.md).

## Choosing a Gemini model

The default is `gemini-3.5-flash-lite` (set `GEMINI_MODEL` to change it). We compared the 8 Gemini models this
key can call on the real heal task, 5 trials each, on two tasks: the permit demo (Chaos Mode breaks the submit
button) and a harder local sandbox where decoy buttons and a decoy search box sit next to the real ones and the
write must actually land. A trial counts only if the heal committed, the next request succeeded on the healed
selector, and the output was correct. Costs are the SDK's estimates, including thinking tokens.

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

- **Accuracy did not separate the models.** Every model healed both tasks 5/5 once an agent that gives up early
  is retried (see below), and none was fooled by the decoys. Cost and speed decide.
- **`gemini-3.5-flash-lite` is about 6x cheaper and 2.2x faster than the previous default,
  `gemini-3.8-flash`** ($0.0052 and 11 s versus $0.0307 and 25 s on the permit demo), and
  about 7x cheaper than `gemini-3.5-flash`. Verified through the dashboard: a heal in about 12 s for $0.005 to $0.0065.
- **Giving up early was the real failure mode.** Before the retry fix, `gemini-3.8-flash` failed 1 of
  5 and `gemini-3.1-pro-preview` 2 of 5 by declaring the task failed partway. The backend now retries that within its
  three-invocation cap, which fixed both (5/5), at a cost: the pro model then needed 1.4 invocations per heal on
  average and took 55 s.
- **Caveats.** Five trials per model on two tasks is a screening, not proof of reliability, and small differences
  between the cheap models are noise. These are preview-era models whose names and prices can change. The 2.5
  family is no longer available to this key. Re-run before a demo on a different site:
  `MENDER_REAL_RUNNER=1 uv run --no-project --python 3.12 --with-requirements services/backend/requirements-live.txt python -B -m services.backend.bench_models --models <a>,<b> --trials 5` (paid; add `--scenario sandbox-hard` for the hard task).
  The raw results are in [benchmarks/model-comparison-2026-10-17.json](benchmarks/model-comparison-2026-10-17.json).
