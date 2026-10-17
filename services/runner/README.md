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
