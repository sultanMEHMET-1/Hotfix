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

The runner reads `contracts/selectors.json`, uses the local portal URL by default, and prints `{"status": "Approved", "inspector": "Davis"}` on success. It caps each navigation and selector step at two seconds, so selector drift reaches recovery quickly. Workflow latency is reported on stderr. When a selector fails, it exits 1 and writes `services/runner/artifacts/failure_latest.png` and `services/runner/artifacts/failure_payload.json`.

`screenshot_path` in the failure payload is always an absolute path, so the backend can open it regardless of its working directory. The DOM snippet comes from the form container, falls back to `main` or `body`, and is capped at 1,500 characters.

After a healer changes `submit_button`, reset the local demo with the portal running:

```bash
services/runner/reset_demo.sh
```

The reset disables Chaos Mode through the portal API and restores `submit_button` to `#submit-btn`. If it changes the selector, it increments the contract version to preserve its monotonic revision rule.
