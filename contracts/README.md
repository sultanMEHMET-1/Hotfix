# Contracts

This directory is the only shared boundary between services. It holds JSON Schema, typed models, workflow definitions, selector maps, and fixtures. It does not contain runners, healers, routes, or UI.

Changing any file here requires a team agreement, except the runtime updates the healer makes to selector maps (every write, including rollback and reset, advances the map's `version`).

## Files

| File | Role |
| --- | --- |
| `workflows/<workflow_id>.json` | A workflow any runner can execute: ordered steps, how each output is read, schemas, a canary. The only place definitions live. |
| `workflow.schema.json` | JSON Schema for a workflow definition (generated from `WorkflowDefinition`). |
| `selectors/<workflow_id>.json` | The selector map for one workflow: its page URL and a CSS selector per field. Rewritten by the healer. |
| `selectors.schema.json` | Schema for a selector map. |
| `failure_payload.schema.json` | Schema for a timeout or selector-miss artifact. |
| `workflow_execution_response.schema.json` | Schema for backend responses, including recovery metadata. |
| `fixtures/mock_failure.json` | Sample failure where `#submit-btn` timed out. |
| `fixtures/workflow_*.json` | Successful, healed, rolled-back, and cooldown responses. |
| `api_types.py` | Pydantic v2 models matching the schemas (`WorkflowDefinition`, `WorkflowSummary`, `WorkflowExecutionResponse`, ...). |
| `api_types.ts` | TypeScript interfaces with the same shapes for the dashboard. |

Today there are two workflows: `permit-application` (the mock permit portal) and `record-update` (a local record editor that really changes a value, so it is marked `mutates`).

## Workflow definitions

`contracts/workflows/<id>.json` describes what to do on a page, independent of any site's selectors:

- `goal` (string): the task in words, given to the repair agent.
- `steps` (ordered list): each `{field, action_type, role?, label?, param?}`. `action_type` is `input` (fill the value of the params key named by `param`) or `click`. `role` and `label` identify the element for the agent's grounding.
- `outputs` (object): output key to `{field, read}`. `read` is `text` (the element's visible text) or `attr:<name>` (one of its attributes). Reads happen after every step, in output order.
- `params_schema` and `output_schema` (JSON Schema): what the caller sends and what comes back. Output values are flat strings.
- `canary` (required): `{params, expected_output, ignore_paths?}`, a known input and its known output. A repair is committed only if replaying the canary reproduces it. `ignore_paths` are JSON Pointers to volatile object fields.
- `mutates` (boolean, default false): the workflow changes data on the site, so the backend runs it only against loopback or allow-listed hosts.

Rules checked when a definition loads: step fields are unique; an input step with outputs defined has a `param`; a field is never both a step and an output; `outputs` cover exactly the properties of `output_schema`, and each is a string.

How repairs treat them: a broken step is repaired by grounding the agent's executed action; a broken **read** is repaired by finding the one element that shows the value the agent reported (this needs at least one `text` output on that field, because an agent cannot see an attribute). Either way the canary decides, and a repaired read must also read back exactly what the agent reported.

## Selector maps

`contracts/selectors/<id>.json` fields:

- `workflow_id` (string, matches the file name and the definition)
- `target_url` (string): the real address of the page the workflow runs on
- `version` (integer, starts at 1)
- `fields` (object): semantic names such as `input_permit_id`, `submit_button`, and `status_badge` mapped to CSS selectors

`target_url` is the single source of truth for the address. The runner opens it, the backend only repairs failures reported from that origin (anything else is rejected as `unexpected_page`), and the backend's write guard checks it. `fields` is a lookup map, not an execution order; the definition's steps and outputs give the order. Stored selectors must be CSS, even when Browser Use provides XPath or accessibility evidence. Every field named by a definition's steps or outputs must exist in its map.

## Failure payload

`failure_payload` required fields:

- `workflow_id` (string)
- `timestamp` (number, unix epoch milliseconds)
- `failed_step` (string): a step field, an output field, or `navigation` when the page did not load (not repairable, no selector is involved)
- `expected_selector` (string)
- `page_url` (string)
- `dom_snippet` (string, broken or shifted markup)
- `screenshot_path` (string)
- `error_message` (string)

## API responses

`GET /api/v1/workflows` returns a list of `WorkflowSummary` (`id`, `goal`, `mutates`, `default`, `params_schema`, `example_params`), default first, so a UI can offer and run any workflow.

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
- `cooldown_remaining_s` (optional nonnegative number)

## Recovery response semantics

The additions are backward compatible: responses without recovery metadata remain valid. Optional nullable fields are accepted by the models and schema; producers should omit unset values with `model_dump(exclude_none=True)`. Never use zero to represent an unknown cost. A measured zero is valid.

The dashboard can display the final response without another request:

- Latency is `execution_time_ms`; workflow output is `data`.
- Show "Browser Use Agent Engaged" when `recovery_attempted` is true, otherwise "Deterministic Playwright". For legacy responses without the flag, fall back to `healed`.
- `status="healed"` and `healed=true` mean the final deterministic replay, output schema validation, and the canary comparison all passed.
- An attempted recovery can end with `status="failed"`, `healed=false`, and an `error`. Failed responses return `data={}`.
- `trace_id` identifies the current request's trace, not a Sentry event ID. It is still populated for local execution when no trace is exported.

Failures are HTTP 200 with `status="failed"`, never an error status. When a recovery was not attempted or produced no candidates, `heal_records` is omitted (equivalent to `[]`), and it is also omitted when restoring the baseline failed (`error.code` `rollback_failed`). `error.message` is always safe to show.

Each `HealRecord` contains:

- `field`: an existing semantic selector-map field (a step or an output field).
- `diff`: the old and candidate new CSS selector.
- `evidence`: action type (`input`, `click`, or `read`), zero-based history step and action index, node name, attributes, mapping reasoning, and optional accessible name and XPath. For an action it describes an executed action correlated with its result; for a read it describes the element whose visible text equals the value the agent reported.
- `verification_outcome`: `committed`, `rolled_back`, or `rejected`.
- `version_before`: selector-map version used to construct the candidate.
- `version_after`: version written when the candidate was installed; omit if rejected before any write.
- `rollback_version`: new version restoring the baseline after an installed candidate was rolled back; omit for committed or never-installed candidates.

Records are returned in candidate-attempt order after the transaction finishes. Forward progress is provisional. A later-step failure can justify another attempt, but no record becomes `committed` until final verification passes. On failure or exhausted attempts, restore baseline selector contents as a new version greater than every provisional version. Mark installed candidates as `rolled_back`; mark candidates rejected before installation as `rejected`. Rolled-back records from one transaction share its final rollback version. Consumers must not apply patches merely because a record exists. Records describe the selector transaction; `status` describes the caller's own run.

The top-level `diff` is the last committed record's diff. Omit it for failed transactions. Use `heal_records` for the complete set of changes, evidence, and version history; do not combine old and new selectors from different fields.

`agent_duration_ms` is the sum of Browser Use agent step durations for the recovery, not end-to-end request latency. Costs and durations cover all attempts. For shared recovery, emit cost and agent duration only on the request that owns the agent run; omit them from joined requests and cooldown hits so aggregating responses does not double-count shared work. If the SDK cannot expose a reliable value, omit it. Joined requests may include the shared records but have their own `trace_id`, `execution_time_ms`, and workflow output from their own replay.

## Failure cooldown

After a failed recovery the backend remembers that exact failure for 15 seconds and answers a repeat of it from memory, without running the agent again. The repeat keeps the original `error` and `heal_records`, has its own `trace_id` and `execution_time_ms`, and carries no `agent_cost_usd` or `agent_duration_ms`. A different failure (another step, selector, or page) starts a fresh recovery. A response served from the cooldown sets `cooldown_remaining_s` to the seconds left before a retry would start a fresh recovery; the field is omitted on every other response, including the failure that started the cooldown. Consumers can show "retry in N s" from it.

## Contract checks

Run from the repository root:

```sh
uv run --no-project --python 3.12 \
  --with-requirements services/backend/requirements-test.txt \
  python -B -m unittest discover -s services/backend/tests -p 'test_contracts.py'
```

The checks use pinned Pydantic v2 and JSON Schema Draft 2020-12 dependencies. Both JSON schemas that describe models are generated from the Pydantic models (`WorkflowExecutionResponse.model_json_schema()` and `WorkflowDefinition.model_json_schema()`, with `$schema` and `$id` headers), and a test fails if a schema drifts from its model. Every definition in `workflows/` must validate, have a selector map of the same name that covers its fields, and survive eight mutations that make a definition ambiguous. Update the TypeScript interfaces alongside any model change.

## Rules of engagement

### Person 1 - `/services/portal` and `/services/runner`

- The runner takes `--contracts <dir>` (default this directory) and `--workflow <id>`, reads `workflows/<id>.json` and `selectors/<id>.json`, opens the map's `target_url`, runs the steps, reads the outputs, and prints one JSON object. It has no site-specific code.
- On timeout or failure, writes `failure_payload.json` that validates against `failure_payload.schema.json`.
- Uses the agreed short per-step timeout (about two seconds for the demo), so a missing selector does not delay recovery for thirty seconds.
- Does not call the vision healer and does not rewrite selectors.

### Person 2 - `/services/backend`

- Consumes `failure_payload.json`.
- Runs the Browser Use healer with Gemini and verifies candidates through the deterministic runner. Uses locked atomic updates (one lock per workflow) and transactional rollback for each selector map; every write, including rollback and reset, advances `version`.
- Returns `WorkflowExecutionResponse` as defined in `api_types.py`, and lists workflows at `GET /api/v1/workflows`.

### Person 3 - `/services/dashboard`

- Consumes `WorkflowExecutionResponse` and `WorkflowSummary` using `contracts/api_types.ts`.
- Does not parse runner artifacts or selector files directly.

## Change control

1. Propose the schema or fixture change in the team channel and wait for agreement from all three owners.
2. Update the JSON Schema, `api_types.py`, and `api_types.ts` in the same change so the three stay identical.
3. Update fixtures so they still validate.
4. Do not land service code in this directory.
