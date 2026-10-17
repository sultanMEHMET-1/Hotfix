# Fast Playwright runner

Install the browser dependency once:

```bash
python -m pip install -r services/runner/requirements.txt
playwright install chromium
```

With the portal running in another terminal, execute the normal workflow:

```bash
python services/runner/execute.py
```

The runner reads `contracts/selectors.json`, uses the local portal URL by default, and prints `{"status": "Approved", "inspector": "Davis"}` on success. Its workflow latency is reported on stderr. When a selector fails, it exits 1 and writes `services/runner/artifacts/failure_latest.png` and `services/runner/artifacts/failure_payload.json`.
