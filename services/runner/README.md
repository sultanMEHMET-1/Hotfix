# Fast Playwright runner

The runner executes any workflow in `contracts/workflows/` against the page named by its selector map in `contracts/selectors/`, with no site-specific code and no LLM. It is the deterministic fast path (about 0.4 s end to end for the permit portal); the backend's repair agent only runs when it fails.

## Setup

Set up the project-local virtual environment once. This installs Python packages into `.venv` and downloads Chromium into `.venv/playwright-browsers`:

```bash
services/runner/setup_venv.sh
```

Start the portal with the same virtual environment:

```bash
.venv/bin/python services/portal/server.py
```

With the portal running in another terminal, run the permit workflow through the venv wrapper:

```bash
services/runner/run.sh
```

The wrapper sets `PLAYWRIGHT_BROWSERS_PATH` to the browser directory inside `.venv`, so the runner does not use a system Python, system site packages, or a user-level Playwright browser cache. To pass runner arguments, append them to the wrapper, for example `services/runner/run.sh --headed`.

## What it does

For `--workflow <id>` it reads `workflows/<id>.json` (steps, outputs) and `selectors/<id>.json` (page URL and a CSS selector per field) from `--contracts` (default: the repository's `contracts/`), then:

1. Opens the map's `target_url` (override with `--target-url`).
2. Runs the ordered steps: each `input` step fills the value of its `param` from `--params`, each `click` step clicks.
3. Reads each output once its element is visible: the element's text, or a named attribute. An empty value counts as a failure.
4. Prints one JSON object on stdout and exits 0.

Every action and read is capped at two seconds, so selector drift reaches recovery quickly. For the permit workflow the output is `{"status": "Approved", "inspector": "Davis", "permit_id": "<submitted id>"}`; the portal echoes the submitted permit id so a wrong repair cannot return the right output. Workflow latency and per-phase timings (`runner_timings_ms`: launch, goto, steps, reads, total) are printed on stderr; the backend attaches the timings to its `runner.execute` span.

A definition is checked with a small hand-written validator (this venv has only Playwright). The runner exits 2 for a configuration problem (unknown workflow, a map for another workflow, a missing param or field, an unreadable definition) and 1 for a workflow failure.

## Backend CLI

The backend calls the runner with `--workflow <id> --params '<json>' --run-id <uuid> --contracts <root>/contracts` (optionally `--sentry-trace` and `--baggage`, which are accepted and ignored). With `--run-id`, failure artifacts go to `runs/<run_id>/` relative to the working directory (`failure_payload.json` and `failure.png`) instead of `services/runner/artifacts/`. Without `--workflow` the runner defaults to `permit-application`, and `--permit-id` and `--applicant-name` still work in place of `--params`. Other flags: `--selectors` (override the map path), `--artifacts-dir`, `--headed`. Set `MENDER_BROWSER_EXECUTABLE` to use a system Chrome instead of the bundled Chromium.

## Failures

When a step or read fails, the runner exits 1 and writes `failure_payload.json` and a screenshot. `failed_step` is the step's field, the output's field, or `navigation` when the page did not load. `screenshot_path` is always an absolute path, so the backend can open it regardless of its working directory. The DOM snippet comes from the form container, falls back to `main` or `body`, and is capped at 1,500 characters.

## Resetting the demo

After a healer changes a selector, reset the local demo with the portal running (the backend should be running too):

```bash
services/runner/reset_demo.sh
```

The reset disables Chaos Mode through the portal API, then restores the selectors through the backend's locked `POST /api/v1/admin/reset` (the backend owns a lock on each selector map, so it must do the write). Only when the connection is refused (no backend is listening) does it edit `contracts/selectors/permit-application.json` itself, restoring `submit_button` to `#submit-btn` and incrementing the version to keep the monotonic revision rule. A timeout or refusal from a running backend (for example while a recovery is in progress) is reported as an error and never bypassed.

## Tests

```bash
cd services/runner && ../../.venv/bin/python -m unittest test_execute
```

These cover the failure artifacts, the definition check, the generic executor against a recording fake page (order, `target_url`, reads, every failure kind, timings), and the reset's fallback rule.
