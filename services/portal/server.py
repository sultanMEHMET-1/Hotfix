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


class PortalState:
    """Process-wide portal state shared by all browser sessions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chaos_enabled = False

    def is_chaos_enabled(self) -> bool:
        with self._lock:
            return self._chaos_enabled

    def set_chaos_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._chaos_enabled = enabled


PORTAL_STATE = PortalState()


def _random_button_class() -> str:
    suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(8))
    return f"legacy-action-{suffix}"


def _page_html(chaos_enabled: bool) -> str:
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
    #chaos-toggle { border: 2px solid #7a0000; border-radius: 3px; padding: 7px 12px;
                    background: #c62828; color: white; cursor: pointer; font-weight: bold; }
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
    <button id="chaos-toggle" type="button" aria-pressed="false">Chaos Mode: OFF</button>
  </nav>
  <main>
    <section class="paper" aria-labelledby="page-title">
      <h1 id="page-title">Permit Application Lookup</h1>
      <p class="notice">Use this form to view the current review status of a municipal permit.</p>
      <form id="permit-form">
        <label for="permit-id">Permit identification number</label>
        <input id="permit-id" name="permit_id" autocomplete="off" required>
        <label for="applicant-name">Applicant name</label>
        <input id="applicant-name" name="applicant_name" autocomplete="off" required>
        <button id="submit-btn" class="btn-primary" type="submit">Submit Application</button>
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
      const toggle = document.querySelector('#chaos-toggle');
      const form = document.querySelector('#permit-form');
      const result = document.querySelector('#result');
      let chaosEnabled = __CHAOS_ENABLED__;

      function updateToggle() {
        toggle.setAttribute('aria-pressed', String(chaosEnabled));
        toggle.textContent = `Chaos Mode: ${chaosEnabled ? 'ON' : 'OFF'}`;
      }

      function applyChaosMode() {
        const button = document.querySelector('#submit-btn');
        if (!button || document.querySelector('#chaos-modal')) return;
        button.removeAttribute('id');
        button.className = `legacy-action-${Math.random().toString(36).slice(2, 10)}`;
        button.setAttribute('data-action', 'submit');
        const modal = document.createElement('div');
        modal.id = 'chaos-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-label', 'Submit application dialog');
        button.replaceWith(modal);
        modal.appendChild(button);
        form.appendChild(modal);
      }

      function applyNormalMode() {
        const modal = document.querySelector('#chaos-modal');
        const button = document.querySelector('[data-action="submit"]');
        if (!modal || !button) return;
        button.removeAttribute('data-action');
        button.className = 'btn-primary';
        button.id = 'submit-btn';
        modal.replaceWith(button);
      }

      toggle.addEventListener('click', async () => {
        toggle.disabled = true;
        try {
          const response = await fetch('/chaos', {
            method: 'POST', headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ enabled: !chaosEnabled })
          });
          if (!response.ok) throw new Error('Could not change Chaos Mode state');
          chaosEnabled = Boolean((await response.json()).enabled);
          updateToggle();
          if (chaosEnabled) applyChaosMode(); else applyNormalMode();
        } finally {
          toggle.disabled = false;
        }
      });

      form.addEventListener('submit', (event) => {
        event.preventDefault();
        result.hidden = false;
      });

      updateToggle();
      if (chaosEnabled) applyChaosMode();
    })();
  </script>
</body>
</html>
""".replace("__CHAOS_ENABLED__", "true" if chaos_enabled else "false")


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
        payload = _page_html(PORTAL_STATE.is_chaos_enabled()).encode("utf-8")
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
            self._send_json(200, {"enabled": PORTAL_STATE.is_chaos_enabled()})
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
            enabled = body["enabled"]
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be a boolean")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
            return
        PORTAL_STATE.set_chaos_enabled(enabled)
        self._send_json(200, {"enabled": enabled})

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
