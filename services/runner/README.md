# Fast Playwright runner

Set up the project-local virtual environment once. This installs Python packages into `.venv` and downloads Chromium into `.venv/playwright-browsers`:

```bash
services/runner/setup_venv.sh
```

Start the portal with the same virtual environment:

```bash
.venv/bin/python services/portal/server.py
```

With the portal running in another terminal, execute the normal workflow through the venv wrapper:

```bash
services/runner/run.sh
```

The wrapper sets `PLAYWRIGHT_BROWSERS_PATH` to the browser directory inside `.venv`, so the runner does not use a system Python, system site packages, or a user-level Playwright browser cache. To pass runner arguments, append them to the wrapper, for example `services/runner/run.sh --headed`.

The runner reads `contracts/selectors.json`, uses the local portal URL by default, and prints `{"status": "Approved", "inspector": "Davis", "permit_id": "<submitted id>"}` on success; the portal echoes the submitted permit id so a wrong repair cannot return the right output. It caps each navigation and selector step at two seconds, so selector drift reaches recovery quickly. Workflow latency is reported on stderr. When a selector fails, it exits 1 and writes `services/runner/artifacts/failure_latest.png` and `services/runner/artifacts/failure_payload.json`.

## Backend CLI

The backend calls the runner with `--workflow <id> --params '<json>' --run-id <uuid>` (optionally
`--sentry-trace` and `--baggage`, which are accepted and ignored). `--params` carries
`permit_id` and `applicant_name`. A workflow id that differs from the selector map's is a
configuration error (exit 2). With `--run-id`, failure artifacts go to `runs/<run_id>/` relative to
the working directory (`failure_payload.json` and `failure.png`) instead of `services/runner/artifacts/`.
Success is exit 0 with one JSON object on stdout. The older flags (`--permit-id`,
`--applicant-name`, `--artifacts-dir`, `--selectors`, `--target-url`, `--headed`) still work.

`screenshot_path` in the failure payload is always an absolute path, so the backend can open it regardless of its working directory. The DOM snippet comes from the form container, falls back to `main` or `body`, and is capped at 1,500 characters.

After a healer changes `submit_button`, reset the local demo with the portal running (the backend should be running too):

```bash
services/runner/reset_demo.sh
```

The reset disables Chaos Mode through the portal API, then restores the selectors through the backend's
locked `POST /api/v1/admin/reset` (the backend owns a lock on `selectors.json`, so it must do the write).
Only when no backend is listening does it edit `contracts/selectors.json` itself, restoring
`submit_button` to `#submit-btn` and incrementing the version to keep the monotonic revision rule.
A refusal from a running backend (for example while a recovery is in progress) is reported as an error
and never bypassed.
