# Mock legacy permit portal

Run the target site from the repository root:

```bash
.venv/bin/python services/portal/server.py
```

Create `.venv` first with `services/runner/setup_venv.sh`. The portal uses only Python's standard library, but using the same project interpreter keeps the complete local workflow inside the venv.

It listens on `http://127.0.0.1:3000/permits/apply`. **Break something** (in the top bar) applies one random change per click, and a note says what changed. The submit button, the permit number box, the applicant name box and the status badge can each break three ways (a new id, a dialog or toolbar, a renamed test id), and decoy buttons plus a quick-search box can appear. At most two fields are broken at once, so a repair never needs more than two agent runs; a click on a broken field breaks it a different way. **Restore site** removes every change. The state is process-wide, so a fresh browser session sees the same changes.

`POST /chaos` drives the same state: `{"next": true}` is one click, `{"break": "button" | "permit" | "applicant" | "read" | "decoys", "variant": 0 to 2}` applies one change, and the original `{"enabled": true}` is the button moving into a dialog (it loses `#submit-btn`, gets a randomized class and `data-action="submit"`), with `{"enabled": false}` restoring everything. `GET /chaos` returns the active changes.

Submitting the form now also stamps the entered permit id on the status badge
(`data-permit`), and the runner returns it as `permit_id`. That lets the backend's canary tell
a correct repair from one that fills the wrong thing.
