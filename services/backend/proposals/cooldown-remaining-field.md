# Proposal: `cooldown_remaining_s` on the workflow response

For the contracts owner (decides) and Person 3 (dashboard). Not applied. Needs sign-off first
because `contracts/` changes require agreement from all three owners.

## Problem

After a failed recovery the backend remembers that exact failure for 15 seconds and answers a
repeat from memory instead of running the agent again. To the dashboard that answer looks like
any other failure, so it cannot tell a viewer "this was cached, retry in N s". Without it, a
presenter who clicks again sees the same error come back instantly and has no explanation.

## The change

One optional field on `WorkflowExecutionResponse`:

```
cooldown_remaining_s: float | None   (>= 0, finite, omitted when unset)
```

Present only on a response served from the failure cooldown: the seconds left before a retry
would start a fresh recovery. Omitted everywhere else, including the failure that started the
cooldown. A cached response still has its own `trace_id` and `execution_time_ms`, keeps the
original `error` and `heal_records`, and carries no `agent_cost_usd` or `agent_duration_ms`.

Backward compatible: older responses stay valid, and the field is optional like
`agent_cost_usd`.

## Alternatives considered

- **`cached: bool`**: says it was cached but not for how long, so no countdown.
- **An HTTP `Retry-After` header**: failures are HTTP 200 by contract, and a header would
  not reach a consumer that reads only the JSON body.
- **Infer it in the dashboard** (same error twice within 15 s): guesses, and breaks when the
  window changes.

## Patches (apply in order from the repository root)

| Patch | Owner | Contents |
| --- | --- | --- |
| `cooldown-1-contracts.patch` | Contracts owner | `api_types.py`, `api_types.ts`, regenerated schema, README section, a `workflow_cooldown.json` fixture, contract test updates |
| `cooldown-2-backend.patch` | Backend (Person 2) | Sets the field on cache hits only, with a test that asserts it on a hit and its absence on the original failure |
| `cooldown-3-dashboard.patch` | Person 3 | Validator accepts the field; the error banner shows "Cached failure: retry in N s", ticks down, then "Cooldown over: a retry will run again"; tests |

`git apply services/backend/proposals/cooldown-1-contracts.patch` (then 2, then 3).

## Verified before proposing

Applied to a scratch copy of the final tree (regenerated after the code review fixes, so they apply to the
current `main`):
- Contract tests pass, including the check that the schema equals the schema generated from
  the model (the schema is regenerated exactly as the owner does it: byte identical before the change).
- Full backend suite: 101 tests pass. The new assertion fails if the backend stops setting the field.
- Dashboard: typecheck, 47 tests (2 new) and the production build pass.
- In a real browser against the real backend: the first failure shows no countdown; the
  cached second failure shows "retry in 12 s", then 9 s three seconds later, then "Cooldown over".
- All three patches apply cleanly from the repository root, alone and together (`git apply --check`).

## Decision needed

Approve the name and meaning of `cooldown_remaining_s`, or ask for a different shape. If
approved, apply patch 1 first; the others depend on it.
