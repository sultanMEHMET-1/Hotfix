# Backend M3: Browser Use recovery with cooldown and repair records

Recovery repairs multiple selectors in one locked transaction, through at most
three agent invocations. Provisional forward progress commits only after
deterministic replay, output validation, and canary verification. Recovery
continues after a client disconnect. A failed recovery is remembered for 15 s,
and every response carries finalized `heal_records`. Stop for M3 review.

## Review and agent handoff

Start with [AGENTS.md](AGENTS.md) for agent operating instructions and
[HANDOFF.md](HANDOFF.md) for the code map, invariants, test evidence, and known
gaps. Reviewers should verify its invariants before approving more
implementation.

## Run

From the repository root, with Python 3.12 and `uv` available:

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements.txt \
  python -m uvicorn services.backend.main:app --env-file services/backend/.env \
  --host 127.0.0.1 --port 8000 --workers 1
```

The local `.env` is ignored by Git. Use `.env.example` as the starting point.
Set `GOOGLE_API_KEY`, `GEMINI_MODEL`, and optionally `SENTRY_DSN`. Missing model
configuration only affects recovery. The deterministic success path imports
neither the healer nor Browser Use. Browser Use imports run in a thread after
a runner failure, so its cold import does not block the server event loop.

The service needs Person 1's runner and a real workflow definition before
integration. No production lookup definition is invented here: the checked-in
selector map still describes `permit-application`, includes an applicant field,
and points at an example URL. Correct that with the contract owner. Requests
with missing definitions or runner configuration return HTTP 503.

POST `/api/v1/run-workflow` with `{"workflow":"your-workflow","params":{...}}`.
Valid execution attempts return HTTP 200 with the shared response model,
with failure represented by `status="failed"`, `healed=false`, and `data={}`.
`error` carries a stable code and a safe message (no keys, paths, prompts, or stack
traces; detail stays in logs and Sentry). `heal_records` lists every candidate that
reached the page, in attempt order, and is omitted when empty. `agent_cost_usd` and
`agent_duration_ms` appear only on the request that ran the agent, only when every
invocation reported them, and never as 0 for unknown. Invalid input returns 422; unknown
configured workflows return 404. The response trace ID is useful in Sentry
when a DSN is set. Traces and Sentry logs are enabled; local operation needs no DSN.

## Real runner and portal (phase-1)

After `services/runner/setup_venv.sh`, run the real Playwright runner and portal tests
(free, mocked agent; add `MENDER_LIVE_TEST=1` for the paid Gemini heal):

```sh
MENDER_REAL_RUNNER=1 uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-live.txt \
  python -B -m unittest services.backend.tests.test_real_runner -v
```

The runner speaks the agreed CLI; the tests use a thin wrapper only to point it at a temp
selector map and portal port. See HANDOFF.md for the gaps and the interim `MENDER_RUNNER_SCRIPT` bridge. The
demo workflow definition is `workflows/permit-application.json`.

## Settings

| Variable | Default |
| --- | --- |
| `MENDER_WORKFLOWS_DIR` | `contracts/workflows/` if it exists, otherwise backend `workflows/` |
| `MENDER_RUNNER_SCRIPT` | Repository `services/runner/execute.py` |
| `MENDER_RUNNER_PYTHON` | Backend Python interpreter |
| `MENDER_RUNNER_TIMEOUT` | 45 seconds per subprocess |
| `MENDER_AGENT_TIMEOUT` | 90 seconds, clamped to the shared remaining recovery budget |
| `MENDER_DEMO_WORKFLOW` | Selector map workflow ID; its definition must include a canary |
| `MENDER_HEADLESS` | `true`; set `false` to display the agent browser |
| `MENDER_BROWSER_EXECUTABLE` | Browser Use's local browser discovery |
| `MENDER_PROPAGATE_TRACE` | `false`; enable only when the runner supports optional trace flags |
| `MENDER_LOG_LEVEL` | `INFO`; use `DEBUG` for detailed SDK console output |

Runner cwd is the repository root. CLI arguments are passed without a shell;
each subprocess gets its own UUID. Only artifacts at `runs/<run_id>/` are used.
Person 1 should use a roughly two-second per-step timeout so broken selectors
reach healing promptly. A runner timeout without failure evidence does not
start a blind browser repair.

## Terminal output

The backend uses Rich for a timestamped, color-aware console timeline:

```text
FAST       Running workflow sample-lookup
BROKEN     Runner exited with a failure
AGENT      Browser Use engaged for submit_button
AGENT      Step 1:
AGENT      Typed the requested record reference
AGENT      Step 2:
AGENT      Clicked the lookup button
PATCH      #old-lookup -> button[data-action="lookup"] (version 2)
VERIFY     Deterministic replay and output schema passed
CANARY     Known lookup matched expected output
HEALED     Recovery verified
```

The live smoke test also prints a result panel with status, total latency,
selector version, old/new selectors, workflow output, and trace ID. The existing
live-test command is unchanged. On failure the panel says recovery failed;
rollback appears as its own timeline event when it occurs.

Emoji and SDK-supplied ANSI escapes are removed in console rendering. Selectors
and bracketed text stay literal; international labels remain readable. Rich
does not force colors when output is redirected. Normal output omits repeated
agent memory/evaluation messages and HTTP/model info chatter. Warnings, errors,
and exception details remain visible. Set `MENDER_LOG_LEVEL=DEBUG` to include
the detailed SDK messages with the same emoji cleanup.

Only console presentation is filtered. Original log records, file handlers,
Sentry context, and workflow response data are preserved. Logs and the result
panel write to stderr, so they do not contaminate a JSON stdout stream.

## Workflow definition

Create `<workflow_id>.json` in the configured folder. `goal` is top-level;
`fields` in the selector map is a lookup, not an execution order.

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
  }
}
```

Every step field must exist in the current selector map. Matching uses executed
actions and results, action type, ordered workflow position, and a unique
role/label. If `label` is omitted, a unique label must be available in the failure
DOM snippet. Missing or ambiguous evidence fails explicitly. CSS is checked
against the live element before use; agent success text is never verification.
Read-only result-element extraction and iframe targets remain unsupported.

Canary exclusions are explicit JSON Pointer paths to object fields, such as
`/updated_at` or `/metadata/request_id`. Raw output must pass its schema before
masking. Missing exclusion paths, root exclusions, array indexing, and masking
all meaningful values are rejected. A canary is required for the demo workflow.
Other workflow definitions may omit one, in which case verification is limited
to successful replay and schema validation.

## Verify and reset

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-test.txt \
  python -B -m unittest discover -s services/backend/tests -v
```

Unit tests mock the agent and use a real subprocess runner double. The recorded
history fixture is a projection of the real Chrome/Browser Use 0.13.11 probe
run with scripted model responses. It covers input and button evidence.

The two opt-in smoke tests make paid Gemini calls against an isolated localhost
fixture, repairing a button and then two broken fields in separate tests. Each
verifies the fix with real Playwright replay and a canary:

```sh
MENDER_LIVE_TEST=1 uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-live.txt \
  python -B -m unittest services.backend.tests.test_live -v
```

On macOS the smoke test discovers Google Chrome; elsewhere set
`MENDER_BROWSER_EXECUTABLE`. Test selectors and backups live in temporary
directories. Product backups live in backend `state/baseline-<run_id>.json`.
Reset with:

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements.txt \
  python -m services.backend.reset services/backend/state/baseline-<run_id>.json
```

## Recovery behavior and client timeouts

Reset, rollback, and execution use the same file lock. One exclusive lock covers
baseline backup, diagnosis, provisional patches, replay, canary, and rollback.
Replay and canary never reacquire it. A later ordered failed step permits another
attempt; a same/earlier failed step aborts. Agent errors, timeouts, and no-result
outcomes may retry the same field within the three-invocation cap. Ambiguous
history or an invalid candidate aborts immediately. All installed patches roll
back together on terminal failure, with a version higher than every provisional
version. No installed candidate means no unnecessary restoration write.

The application retains one active background recovery task per workflow.
Requests join through a shield; disconnecting or cancelling one request does not
stop healing. Successful waiters replay using their own parameters and run IDs.
Failure returns the same failed outcome to existing waiters. Graceful application
shutdown waits for active recoveries.

## Failure cooldown and heal records

After cleanup finishes, one failed recovery per workflow is kept in memory for
15 s (`failure_cooldown`, event loop monotonic clock). A later runner failure that
matches on workflow, failed step, old selector, the whole selector map (after
cleanup, so a rollback's higher version is included) and a hash of the failure
artifact's page URL, DOM snippet and error message gets the original error and
records back with no agent, no writes, and no new measurement file. Any difference
starts a fresh recovery. Hits never extend expiry, a backend restart clears the
cache, and a `COOLDOWN` log line names the originating recovery and time left.
Configuration errors, failures without valid runner evidence, cancellations, and
failed cleanup or restoration are never cached. Deterministic execution continues
during cooldown.

Each record is `committed` (final replay, schema and canary passed), `rolled_back`
(installed, then the transaction failed and the baseline was restored; all share
one `rollback_version`), or `rejected` (a grounded candidate refused before it was
written, with no `version_after`). Agent errors, empty results, and ambiguous
evidence stay log and Sentry events. Records describe the selector transaction;
`status` describes the caller's own run, so a waiter whose replay fails after a
shared heal keeps the committed records, its own error, and no `diff`. If baseline
restoration fails, records are omitted, `error.code` is `rollback_failed`, and the
backend blocks execution (HTTP 503) until restored and restarted.

## Operator commands

Loopback callers only:

```sh
curl -X POST localhost:8000/api/v1/admin/reset   # restore committed selectors, clear cooldown (409 during a recovery)
curl localhost:8000/api/v1/status                # blocked reason, active recoveries, cooldown seconds left
```

Reset restores `contracts/selectors.json` from git `HEAD` as a new higher version.
Do not commit a healed selector map or HEAD stops being the original. With the
server stopped, `python -m services.backend.reset --original` does the file part.
After `rollback_failed` the backup path is in the ERROR log; run
`python -m services.backend.reset services/backend/state/baseline-<run_id>.json`
then restart.

Recovery has one 240-second monotonic budget, starting before exclusive-lock
waiting. Recovery work stops at 210 seconds, reserving 30 seconds for emergency
browser/process cleanup and rollback. Ordinary shutdown also consumes work time.
Per-agent and per-runner timeouts cannot extend the recovery deadline. Ordinary
fast-path lock acquisition is bounded to five seconds; requests join a known
active recovery instead of failing that wait. Lock timeout detail is in logs and
Sentry; the API returns a failed execution response with a trace ID.

**Clients and proxies must allow at least 240 seconds plus initial runner time,
any waiter replay, and network overhead.** Client timeout does not undo or cancel
a repair. The initial deterministic run is outside the recovery budget. Forced
termination, process crashes, and blocked OS/filesystem operations are outside
this application-level deadline guarantee. Cleanup/restoration failures block
further execution until operator recovery and restart.

## Selector derivation

Candidates are tried in this order: `data-testid`, `data-test`, `data-action`,
`data-field`, then `id`, `name`, `aria-label`, a unique tag, and structural CSS.
Structural fallback walks the live DOM, using ancestor attributes, direct-child
combinators, and `:nth-of-type()` where needed. Classes are not used. Each
candidate must select exactly one element and that element must be the agent's
interacted node. XPath identifies the live node but is never stored as CSS.

Structural selectors depend on DOM structure and may break on later reordering.
Real runner replay and the canary remain mandatory acceptance checks. Missing,
detached, iframe, or otherwise unresolved targets fail explicitly; terminal
failure restores all provisional changes. There is no blind first-match fallback.

Run real DOM checks without Gemini calls:

```sh
MENDER_BROWSER_TEST=1 uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-live.txt \
  python -B -m unittest services.backend.tests.test_selectors -v
```

These cover class-only chaos with a stable attribute, structural fallback when
only a class remains, attribute escaping, and a missing live target. The ordinary
suite mocks Browser Use and skips these browser checks and both paid live tests.

## Live measurements

The live command retains sanitized JSON reports under ignored
`services/backend/state/live-<scenario>-<recovery_id>.json`, even though its portal,
selectors, failure screenshots, and backups are temporary. Live reports also record the response's cost, agent duration, and records. Reports contain Python
and SDK versions, model, request/recovery/test wall-clock times, per-invocation
wall-clock times, and SDK token usage. Cached tokens are reported separately as
a subset of prompt usage, not added twice. Total token count follows the SDK's
prompt-plus-completion convention. Unknown usage/cost is omitted and completeness
flags distinguish partial totals. These reports contain no API keys or prompts.

Ordinary recoveries also retain `state/recovery-<id>.json` and log the same
measurements once per background task. Joined requests do not duplicate usage.
SDK step duration is not substituted for measured wall-clock time. SDK costs
are optional estimates, not billing receipts. See HANDOFF.md for measured runs.

## Rehearse the demo

Start the portal (`.venv/bin/python services/portal/server.py`)
and the backend (see Run), then `python -m services.backend.rehearse 5`. Each loop resets,
runs the fast path, enables Chaos Mode, heals with the paid agent, and runs fast again. It
exits with `N/N PASS`.
