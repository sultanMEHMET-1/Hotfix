# Backend M1: Browser Use recovery

M1 repairs one selector per request, verifies it with the deterministic runner
and optional canary, and rolls back on any verification failure. Review M1
before continuing to multi-field recovery (M2) or shared recovery tasks and
heal-record responses (M3).

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
including a structured error on failure. Invalid input returns 422; unknown
configured workflows return 404. The response trace ID is useful in Sentry
when a DSN is set. Traces and Sentry logs are enabled; local operation needs no DSN.

## Settings

| Variable | Default |
| --- | --- |
| `MENDER_WORKFLOWS_DIR` | `contracts/workflows/` if it exists, otherwise backend `workflows/` |
| `MENDER_RUNNER_SCRIPT` | Repository `services/runner/execute.py` |
| `MENDER_RUNNER_PYTHON` | Backend Python interpreter |
| `MENDER_RUNNER_TIMEOUT` | 45 seconds per subprocess |
| `MENDER_AGENT_TIMEOUT` | 90 seconds, plus a 15-second browser shutdown budget and emergency process cleanup |
| `MENDER_HEADLESS` | `true`; set `false` to display the agent browser |
| `MENDER_BROWSER_EXECUTABLE` | Browser Use's local browser discovery |
| `MENDER_PROPAGATE_TRACE` | `false`; enable only when the runner supports optional trace flags |

Runner cwd is the repository root. CLI arguments are passed without a shell;
each subprocess gets its own UUID. Only artifacts at `runs/<run_id>/` are used.
Person 1 should use a roughly two-second per-step timeout so broken selectors
reach healing promptly. A runner timeout without failure evidence does not
start a blind browser repair.

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
Read-only result-element extraction and iframe targets are not supported in M1.

Canary exclusions are explicit JSON Pointer paths to object fields, such as
`/updated_at` or `/metadata/request_id`. Raw output must pass its schema before
masking. Missing exclusion paths, root exclusions, array indexing, and masking
all meaningful values are rejected. Without a canary, schema validation cannot
detect every semantically incorrect result.

## Verify and reset

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-test.txt \
  python -B -m unittest discover -s services/backend/tests -v
```

Unit tests mock the agent and use a real subprocess runner double. The recorded
history fixture is a projection of the real Chrome/Browser Use 0.13.11 probe
run with scripted model responses. It covers input and button evidence.

The opt-in smoke test makes paid Gemini calls against an isolated localhost
fixture, then verifies the fix with real Playwright replay and a canary:

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

Reset, rollback, and execution use the same file lock. Restoring selector
contents always creates a higher version. M1 holds the exclusive lock through
agent diagnosis, patch, replay, and canary, so other requests cannot consume
a provisional selector. This serializes access to the one configured workflow.
M2 adds accumulated provisional patches, three attempts, and a recovery-wide
240-second deadline. M3 adds per-workflow single-flight, failure cooldown,
shared-flight accounting, and structured heal-record responses.
