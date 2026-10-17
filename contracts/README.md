# Contracts

This directory is the only shared boundary between services. It holds JSON Schema, typed models, and fixtures. It does not contain runners, healers, routes, or UI.

Changing any file here requires a team agreement. No developer may edit files outside their designated service directory, and no developer may edit `/contracts` alone.

## Files

| File | Role |
| --- | --- |
| `selectors.schema.json` | Schema for deterministic element targeting. |
| `selectors.json` | Default selector map for the sample permit workflow. |
| `failure_payload.schema.json` | Schema for a timeout or selector-miss artifact. |
| `fixtures/mock_failure.json` | Sample failure where `#submit-btn` timed out. |
| `api_types.py` | Pydantic v2 models matching the schemas, plus `WorkflowExecutionResponse`. |
| `api_types.ts` | TypeScript interfaces with the same shapes for the dashboard. |

`selectors.json` fields:

- `workflow_id` (string)
- `target_url` (string)
- `version` (integer)
- `fields` (object): semantic names such as `input_permit_id`, `submit_button`, and `status_badge` mapped to CSS selectors

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

## Rules of engagement

### Person 1 — `/services/portal` and `/services/runner`

- Reads `contracts/selectors.json` (validated by `selectors.schema.json`) as the only source of element targets.
- On timeout or failure, writes `failure_payload.json` that validates against `failure_payload.schema.json`.
- Does not call the vision healer and does not rewrite selectors.

### Person 2 — `/services/backend`

- Consumes `failure_payload.json`.
- Runs the vision healer and, when a replacement selector is accepted, updates `contracts/selectors.json` and increments `version`.
- Returns `WorkflowExecutionResponse` as defined in `api_types.py`.

### Person 3 — `/services/dashboard`

- Consumes `WorkflowExecutionResponse` using `contracts/api_types.ts`.
- Does not parse runner artifacts or selector files directly.

## Change control

1. Propose the schema or fixture change in the team channel and wait for agreement from all three owners.
2. Update the JSON Schema, `api_types.py`, and `api_types.ts` in the same change so the three stay identical.
3. Update fixtures so they still validate.
4. Do not land service code in this directory.
