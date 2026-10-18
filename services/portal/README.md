# Mock legacy permit portal

Run the target site from the repository root:

```bash
.venv/bin/python services/portal/server.py
```

Create `.venv` first with `services/runner/setup_venv.sh`. The portal uses only Python's standard library, but using the same project interpreter keeps the complete local workflow inside the venv.

It listens on `http://127.0.0.1:3000/permits/apply`. The red Chaos Mode button changes process-wide state, so a fresh browser session sees the same mode. In Chaos Mode the submit button loses `#submit-btn`, receives a randomized class and `data-action="submit"`, and is moved into a modal container.
