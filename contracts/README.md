# Contracts

This directory is the only shared boundary between services. It holds JSON Schema, typed models, and fixtures. It does not contain runners, healers, routes, or UI.

Changing any file here requires a team agreement. No developer may edit files outside their designated service directory, and no developer may edit `/contracts` alone.

## Files

| File | Role |
| --- | --- |
| `selectors.schema.json` | Schema for deterministic element targeting. |
| `selectors.json` | Default selector map for the sample permit workflow. |
| `failure_payload.schema.json` | Schema for a timeout or selector-miss artifact. |
| `workflow_execution_response.schema.json` | Schema for backend responses, including recovery metadata. |
| `fixtures/mock_failure.json` | Sample failure where `#submit-btn` timed out. |
| `fixtures/workflow_*.json` | Successful, healed, and transactionally rolled-back responses. |
| `api_types.py` | Pydantic v2 models matching the schemas, plus `WorkflowExecutionResponse`. |
| `api_types.ts` | TypeScript interfaces with the same shapes for the dashboard. |

`selectors.json` fields:

- `workflow_id` (string)
- `target_url` (string)
- `version` (integer)
- `fields` (object): semantic names such as `input_permit_id`, `submit_button`, and `status_badge` mapped to CSS selectors

`fields` is a lookup map, not an execution order. Ordered steps and the top-level
`goal` belong to backend-owned workflow definitions for now. The selector map
still describes one workflow. Stored selectors must be CSS, even when Browser
Use provides XPath or accessibility evidence.

`failure_payload` required fields:

- `workflow_id` (string)
- `timestamp` (number, unix epoch milliseconds)
- `failed_step` (string)
- `expected_selector` (string)
- `page_url` (string)
- `dom_snippet` (string, broken or shifted markup)
- `screenshot_path` (string)
- `error_message` (string)

`WorkflowExecutionResponse` fields:

- `status`: `"success"` | `"healed"` | `"failed"`
- `execution_time_ms` (float)
- `data` (object)
- `healed` (boolean)
- `trace_id` (string)
- `diff` (optional object with `old_selector` and `new_selector`)
- `recovery_attempted` (optional boolean, defaults to `false` for legacy payloads)
- `error` (optional object with nonempty `code` and `message`)
- `heal_records` (optional array, defaults to empty)
- `agent_cost_usd` (optional nonnegative number)
- `agent_duration_ms` (optional nonnegative number)

## Recovery response semantics

The additions are backward compatible: responses without recovery metadata
remain valid. Optional nullable fields are accepted by the models and schema;
producers should omit unset values with `model_dump(exclude_none=True)`.
Never use zero to represent an unknown cost. A measured zero is valid.

The dashboard can display the final response without another request:

- Latency is `execution_time_ms`; workflow output is `data`.
- Show "Browser Use Agent Engaged" when `recovery_attempted` is true, otherwise
  "Deterministic Playwright". For legacy responses without the flag, fall back
  to `healed`.
- `status="healed"` and `healed=true` mean the final deterministic replay,
  output schema validation, and optional canary comparison all passed.
- An attempted recovery can end with `status="failed"`, `healed=false`, and an
  `error`. Failed responses return `data={}`.
- `trace_id` identifies the current request's trace, not a Sentry event ID.
  It is still populated for local execution when no trace is exported.

Each `HealRecord` contains:

- `field`: an existing semantic selector-map field.
- `diff`: the old and candidate new CSS selector.
- `evidence`: action type, zero-based history step and action index, node name,
  attributes, mapping reasoning, and optional accessible name and XPath.
  This must describe an executed action correlated with its result. Supporting
  read-only element extraction remains a stretch.
- `verification_outcome`: `committed`, `rolled_back`, or `rejected`.
- `version_before`: selector-map version used to construct the candidate.
- `version_after`: version written when the candidate was installed; omit if
  rejected before any write.
- `rollback_version`: new version restoring the baseline after an installed
  candidate was rolled back; omit for committed or never-installed candidates.

Records are returned in candidate-attempt order after the transaction finishes.
Forward progress is provisional. A later-step failure can justify another
attempt, but no record becomes `committed` until final verification passes.
On failure or exhausted attempts, restore baseline selector contents as a new
version greater than every provisional version. Mark installed candidates as
`rolled_back`; mark candidates rejected before installation as `rejected`.
Rolled-back records from one transaction share its final rollback version.
Consumers must not apply patches merely because a record exists.

The top-level `diff` is the last committed record's diff. Omit it for failed
transactions. Use `heal_records` for the complete set of changes, evidence,
and version history; do not combine old and new selectors from different fields.

`agent_duration_ms` is the sum of Browser Use agent step durations for the
recovery, not end-to-end request latency. Costs and durations cover all attempts.
For shared recovery, emit cost and agent duration only on the request that owns
the agent run; omit them from joined requests so aggregating responses does not
double-count shared work. If the SDK cannot expose a reliable value, omit it.
Joined requests may include the shared records but have their own `trace_id`,
`execution_time_ms`, and workflow output from their own replay.

## Contract checks

Run from the repository root:

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-test.txt \
  python -B -m unittest discover -s services/backend/tests -p 'test_contracts.py'
```

The checks use pinned Pydantic v2 and JSON Schema Draft 2020-12 dependencies.
The response JSON schema is
generated from `WorkflowExecutionResponse.model_json_schema()` with the
`$schema` and `$id` headers; update the TypeScript interfaces alongside it.

## Rules of engagement

### Person 1 — `/services/portal` and `/services/runner`

- Reads `contracts/selectors.json` (validated by `selectors.schema.json`) as the only source of element targets.
- On timeout or failure, writes `failure_payload.json` that validates against `failure_payload.schema.json`.
- Uses the agreed short per-step timeout (about two seconds for the demo), so a
  missing selector does not delay recovery for thirty seconds.
- Does not call the vision healer and does not rewrite selectors.

### Person 2 — `/services/backend`

- Consumes `failure_payload.json`.
- Runs the Browser Use healer with Gemini and verifies candidates through the
  deterministic runner. Uses locked atomic updates and transactional rollback
  for `contracts/selectors.json`; every write, including rollback and reset,
  advances `version`.
- Returns `WorkflowExecutionResponse` as defined in `api_types.py`.

### Person 3 — `/services/dashboard`

- Consumes `WorkflowExecutionResponse` using `contracts/api_types.ts`.
- Does not parse runner artifacts or selector files directly.

## Change control

1. Propose the schema or fixture change in the team channel and wait for agreement from all three owners.
2. Update the JSON Schema, `api_types.py`, and `api_types.ts` in the same change so the three stay identical.
3. Update fixtures so they still validate.
4. Do not land service code in this directory.
