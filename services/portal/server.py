#!/usr/bin/env python3
"""Small, stateful legacy permit portal used by the runner demo."""

from __future__ import annotations

import argparse
import json
import random
import string
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3000


# Each field a workflow selects can break in several ways; variant 0 of "button" is the original Chaos Mode.
VARIANTS = {
    "button": ["The submit button moved into a dialog and lost its id.", "The submit button was given a new id.",
               "The submit button moved into a toolbar and lost its id."],
    "permit": ["The permit number box was given a new id.", "The permit number box was renamed to a case reference.",
               "The permit number box was renamed to a filing code."],
    "applicant": ["The applicant name box was given a new id.", "The applicant name box was renamed to a filer name.",
                  "The applicant name box was renamed to a party name."],
    "read": ["The status badge's test id was renamed.", "The status badge's test id was changed to a decision label.",
             "The status badge lost its test id and got a data field instead."],
}
MAX_SELECTOR_BREAKS = 2  # a repair fixes one field per agent run and runs at most three, so keep a spare
DECOYS_MESSAGE = "Decoy buttons and a quick-search box appeared."


class PortalState:
    """Process-wide portal state shared by all browser sessions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._variants: dict[str, int] = {}
        self._decoys = False
        self._last: str | None = None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            last = self._last
            message = DECOYS_MESSAGE if last == "decoys" else VARIANTS[last][self._variants[last]] if last in self._variants else None
            return {"enabled": bool(self._variants) or self._decoys, "variants": dict(self._variants), "decoys": self._decoys,
                    "last": {"key": last, "message": message} if message else None}

    def is_chaos_enabled(self) -> bool:
        return bool(self.snapshot()["enabled"])

    def set_chaos_enabled(self, enabled: bool) -> None:
        """The original on/off switch: on is the button moving into a dialog, off restores everything."""
        with self._lock:
            self._variants = {"button": 0} if enabled else {}
            self._decoys = False
            self._last = "button" if enabled else None

    def apply(self, key: str, variant: int = 0) -> None:
        with self._lock:
            if key == "decoys":
                self._decoys = True
            elif key in VARIANTS and 0 <= variant < len(VARIANTS[key]):
                self._variants[key] = variant
            else:
                raise ValueError("unknown change")
            self._last = key

    def next_break(self, rng: random.Random | None = None) -> None:
        """One random change per click. A field already broken is broken a different way, so it never runs out."""
        rng = rng or random
        with self._lock:
            capped = len(self._variants) >= MAX_SELECTOR_BREAKS
            pool = [(key, n) for key, texts in VARIANTS.items() for n in range(len(texts))
                    if (key in self._variants or not capped) and self._variants.get(key) != n]
            if not self._decoys:
                pool.append(("decoys", 0))
        key, variant = rng.choice(pool)
        self.apply(key, variant)


PORTAL_STATE = PortalState()


def _random_button_class() -> str:
    suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(8))
    return f"legacy-action-{suffix}"


def _page_html(state: dict[str, object]) -> str:
    """Return the stable page shell; JavaScript applies shared chaos state."""

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>City Permit Records</title>
  <style>
    :root { color-scheme: light; font-family: Arial, sans-serif; }
    body { margin: 0; background: #e7e3d8; color: #292929; }
    nav { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px;
          background: #243b53; color: white; border-bottom: 4px solid #152536; }
    nav strong { letter-spacing: .04em; }
    .controls { display: flex; gap: 8px; } #chaos-note { margin-left: auto; margin-right: 16px; font-size: 13px; color: #d9e2ec; }
    #break-btn, #restore-btn { border: 2px solid #7a0000; border-radius: 3px; padding: 7px 12px;
                    background: #c62828; color: white; cursor: pointer; font-weight: bold; }
    #restore-btn { background: #fffef8; color: #7a0000; } button:disabled { opacity: .5; cursor: not-allowed; }
    #decoys { margin-top: 14px; display: flex; gap: 10px; } #decoys button { padding: 8px 12px; border: 1px solid #777; background: #eee; cursor: pointer; }
    #quick-search-slot { margin-bottom: 8px; }
    #action-bar { margin-top: 18px; border: 2px solid #805744; padding: 12px; background: #f5eee4; }
    main { max-width: 760px; margin: 34px auto; padding: 0 18px; }
    .paper { background: #fffef8; border: 1px solid #aaa; box-shadow: 2px 3px 0 #aaa; padding: 26px; }
    h1 { margin-top: 0; font-family: Georgia, serif; font-size: 28px; }
    .notice { padding: 10px; border-left: 5px solid #d49b2a; background: #fff8db; }
    label { display: block; margin: 16px 0 6px; font-weight: bold; }
    input { display: block; width: min(100%, 420px); box-sizing: border-box; padding: 9px;
            border: 1px solid #777; border-radius: 2px; font-size: 16px; }
    #submit-btn, [data-action="submit"] { margin-top: 20px; padding: 10px 18px; border: 1px solid #184d2b;
            background: #2e7d32; color: white; font-weight: bold; cursor: pointer; }
    #chaos-modal { margin-top: 18px; border: 2px solid #8b1e1e; padding: 12px; background: #fff1f1; }
    #chaos-modal::before { content: "Legacy dialog"; display: block; margin-bottom: 4px;
                           color: #8b1e1e; font-size: 12px; font-weight: bold; text-transform: uppercase; }
    #result { margin-top: 22px; padding: 14px; border: 1px solid #356859; background: #e8f5e9; }
    #result[hidden] { display: none; }
    #status-badge { font-weight: bold; }
    .fine-print { margin-top: 22px; color: #666; font-size: 12px; }
  </style>
</head>
<body>
  <nav>
    <strong>DEPARTMENT OF BUILDING SERVICES · PUBLIC RECORDS</strong>
    <span id="chaos-note" role="status"></span>
    <span class="controls"><button id="break-btn" type="button">Break something</button>
    <button id="restore-btn" type="button" disabled>Restore site</button></span>
  </nav>
  <main>
    <section class="paper" aria-labelledby="page-title">
      <h1 id="page-title">Permit Application Lookup</h1>
      <p class="notice">Use this form to view the current review status of a municipal permit.</p>
      <div id="quick-search-slot"></div>
      <form id="permit-form">
        <label for="permit-id" data-for="permit_id">Permit identification number</label>
        <input id="permit-id" name="permit_id" autocomplete="off" required>
        <label for="applicant-name" data-for="applicant_name">Applicant name</label>
        <input id="applicant-name" name="applicant_name" autocomplete="off" required>
        <button id="submit-btn" class="btn-primary" type="submit">Submit Application</button>
        <div id="decoys"></div>
        <div id="result" hidden aria-live="polite">
          <span data-testid="status-badge" data-status="Approved" data-inspector="Davis">Approved</span>
          <span> · Inspector: Davis</span>
        </div>
      </form>
      <p class="fine-print">Records are refreshed during regular office hours. Keep your confirmation number.</p>
    </section>
  </main>
  <script>
    (() => {
      const form = document.querySelector('#permit-form');
      const result = document.querySelector('#result');
      const badge = result.querySelector('[data-status]');
      const permit = form.elements.permit_id, applicant = form.elements.applicant_name;
      const button = document.querySelector('#submit-btn');
      const breakBtn = document.querySelector('#break-btn'), restoreBtn = document.querySelector('#restore-btn');
      const note = document.querySelector('#chaos-note');
      let state = __STATE__, pending = false;

      function labelFor(field, id) { field.id = id; form.querySelector(`label[data-for="${field.name}"]`).htmlFor = id; }

      function wrapButton(kind) {
        button.removeAttribute('id');
        button.className = `legacy-action-${Math.random().toString(36).slice(2, 10)}`;
        button.setAttribute('data-action', 'submit');
        if (kind === 1) { button.id = 'commit-btn'; button.removeAttribute('data-action'); return; }
        const box = document.createElement('div');
        box.id = kind === 0 ? 'chaos-modal' : 'action-bar';
        box.setAttribute('role', kind === 0 ? 'dialog' : 'toolbar');
        box.setAttribute('aria-label', kind === 0 ? 'Submit application dialog' : 'Application actions');
        button.replaceWith(box);
        box.appendChild(button);
        form.insertBefore(box, document.querySelector('#decoys'));
      }

      function apply(next) {
        state = next;
        const v = next.variants || {};
        const holder = button.parentElement;
        if (holder.id === 'chaos-modal' || holder.id === 'action-bar') holder.replaceWith(button);
        button.removeAttribute('data-action'); button.className = 'btn-primary'; button.id = 'submit-btn';
        if ('button' in v) wrapButton(v.button);
        labelFor(permit, 'permit' in v ? ['permit-no', 'case-ref', 'filing-code'][v.permit] : 'permit-id');
        labelFor(applicant, 'applicant' in v ? ['filer', 'filer-name', 'party-name'][v.applicant] : 'applicant-name');
        badge.removeAttribute('data-field');
        badge.setAttribute('data-testid', 'read' in v ? ['status-value', 'decision', ''][v.read] : 'status-badge');
        if ('read' in v && v.read === 2) { badge.removeAttribute('data-testid'); badge.setAttribute('data-field', 'status'); }
        const decoys = document.querySelector('#decoys'), slot = document.querySelector('#quick-search-slot');
        if (next.decoys && !decoys.firstChild) {
          decoys.innerHTML = '<button type="button">Save draft</button><button type="button">Request certified copy</button>';
          slot.innerHTML = '<input id="quick-search" aria-label="Quick search" placeholder="Quick search" autocomplete="off">';
        } else if (!next.decoys) { decoys.replaceChildren(); slot.replaceChildren(); }
        note.textContent = next.last ? `Last change: ${next.last.message}` : '';
        restoreBtn.disabled = pending || !next.enabled;
      }

      async function change(body) {
        if (pending) return;
        pending = true; breakBtn.disabled = true; restoreBtn.disabled = true;
        try {
          const response = await fetch('/chaos', {
            method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
          });
          if (!response.ok) throw new Error('Could not change the site');
          apply(await response.json());
        } finally {
          pending = false; breakBtn.disabled = false; apply(state);
        }
      }

      breakBtn.addEventListener('click', () => change({ next: true }));
      restoreBtn.addEventListener('click', () => change({ enabled: false }));

      form.addEventListener('submit', (event) => {
        event.preventDefault();
        badge.setAttribute('data-permit', permit.value);
        result.hidden = false;
      });

      apply(state);
    })();
  </script>
</body>
</html>
""".replace("__STATE__", json.dumps(state))


class PortalRequestHandler(BaseHTTPRequestHandler):
    server_version = "MenderLegacyPortal/1.0"

    def _send_json(self, status_code: int, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self) -> None:
        payload = _page_html(PORTAL_STATE.snapshot()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlsplit(self.path).path
        if path in {"/", "/permits/apply"}:
            self._send_html()
        elif path == "/chaos":
            self._send_json(200, PORTAL_STATE.snapshot())
        elif path == "/healthz":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if urlsplit(self.path).path != "/chaos":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
            if body.get("next"):
                PORTAL_STATE.next_break()
            elif "break" in body:
                PORTAL_STATE.apply(str(body["break"]), int(body.get("variant", 0)))
            else:
                enabled = body["enabled"]
                if not isinstance(enabled, bool):
                    raise ValueError("enabled must be a boolean")
                PORTAL_STATE.set_chaos_enabled(enabled)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
            return
        self._send_json(200, PORTAL_STATE.snapshot())

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"[portal] {format_string % args}")


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), PortalRequestHandler)
    print(f"Legacy permit portal listening at http://{host}:{port}/permits/apply")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPortal stopped.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
