#!/usr/bin/env python3
"""Local stateful site for write workflows: edit a record, read the saved value back.

Public sites cannot be modified, so write workflows are exercised here. State is in
memory. Chaos Mode breaks the save button the same way the permit portal breaks its
submit button. With hard=true it also adds decoys (a search box, "Save draft" and "Clear form"
buttons) that a weak agent could use by mistake. With read=true the saved value's test id is renamed
(saved-value to result-value), so the selector that READS the result breaks while the form still works. GET /state shows the stored records and how many writes happened, so a
test can prove repeated replays leave the same result. POST /reset clears everything.
"""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOCK = threading.Lock()
STATE = {"records": {}, "writes": 0, "chaos": False, "hard": False, "read": False}

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Record Editor</title>
<style>
body { font-family: Arial, sans-serif; margin: 0; background: #eef1f5; }
nav { display: flex; justify-content: space-between; padding: 12px 20px; background: #1f3a5f; color: white; }
main { max-width: 640px; margin: 30px auto; padding: 24px; background: white; border: 1px solid #ccd; }
label { display: block; margin: 14px 0 6px; font-weight: bold; }
input { display: block; width: 100%; box-sizing: border-box; padding: 8px; font-size: 16px; }
#save-btn, [data-action="save"] { margin-top: 18px; padding: 9px 16px; background: #2563eb; color: white; border: 0; }
#chaos-modal { margin-top: 16px; padding: 10px; border: 2px solid #8b1e1e; background: #fff1f1; }
#result { margin-top: 18px; padding: 12px; background: #e8f5e9; } #result[hidden] { display: none; }
</style></head><body>
<nav><strong>RECORD EDITOR</strong>__SEARCH__<button id="chaos-toggle" type="button">Chaos Mode: OFF</button></nav>
<main><h1>Edit a record</h1>
<form id="record-form">
<label for="record-id">Record ID</label><input id="record-id" name="record_id" autocomplete="off" required>
<label for="record-value">New value</label><input id="record-value" name="value" autocomplete="off" required>
__DECOYS__<button id="save-btn" class="btn-primary" type="submit">Save record</button>
<div id="result" hidden aria-live="polite"><span>Saved </span><span id="out-record" data-testid="saved-record"></span><span> = </span><span id="out-value" data-testid="__VALUE_ID__"></span></div>
</form></main>
<script>
(() => {
  const form = document.querySelector('#record-form'), toggle = document.querySelector('#chaos-toggle');
  let chaos = __CHAOS__;
  function label() { toggle.textContent = `Chaos Mode: ${chaos ? 'ON' : 'OFF'}`; }
  function breakButton() {
    const button = document.querySelector('#save-btn');
    if (!button || document.querySelector('#chaos-modal')) return;
    button.removeAttribute('id');
    button.className = `legacy-${Math.random().toString(36).slice(2, 10)}`;
    button.setAttribute('data-action', 'save');
    const modal = document.createElement('div');
    modal.id = 'chaos-modal'; modal.setAttribute('role', 'dialog'); modal.setAttribute('aria-label', 'Save record dialog');
    button.replaceWith(modal); modal.appendChild(button); form.appendChild(modal);
  }
  function fixButton() {
    const modal = document.querySelector('#chaos-modal'), button = document.querySelector('[data-action="save"]');
    if (!modal || !button) return;
    button.removeAttribute('data-action'); button.className = 'btn-primary'; button.id = 'save-btn'; modal.replaceWith(button);
  }
  toggle.addEventListener('click', async () => {
    const reply = await fetch('/chaos', {method: 'POST', body: JSON.stringify({enabled: !chaos})});
    chaos = (await reply.json()).enabled; label(); chaos ? breakButton() : fixButton();
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const reply = await fetch('/records', {method: 'POST', body: JSON.stringify({
      record_id: document.querySelector('#record-id').value, value: document.querySelector('#record-value').value})});
    const saved = await reply.json();
    document.querySelector('#out-record').textContent = saved.record_id;
    document.querySelector('#out-value').textContent = saved.value;
    document.querySelector('#result').hidden = false;
  });
  label(); if (chaos) breakButton();
})();
</script></body></html>"""


SEARCH = '<input aria-label="Search records" placeholder="Search records" style="width:220px">'
DECOYS = ('<button type="button" data-action="draft" style="margin-top:18px;margin-right:8px">Save draft</button>'
          '<button type="button" id="clear-btn" style="margin-top:18px;margin-right:8px">Clear form</button>')


def render():
    page = PAGE.replace("__CHAOS__", "true" if STATE["chaos"] else "false")
    value_id = "result-value" if STATE["read"] else "saved-value"
    return (page.replace("__SEARCH__", SEARCH if STATE["hard"] else "").replace("__DECOYS__", DECOYS if STATE["hard"] else "")
            .replace("__VALUE_ID__", value_id))


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, kind="application/json"):
        payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def body(self):
        length = min(int(self.headers.get("Content-Length", "0")), 10_000)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlsplit(self.path).path
        with LOCK:
            if path in {"/", "/records"}:
                return self.reply(200, render(), "text/html")
            if path == "/state":
                return self.reply(200, STATE)
        self.reply(200 if path == "/healthz" else 404, {"status": "ok"} if path == "/healthz" else {"error": "not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            data = self.body()
            with LOCK:
                if path == "/records":
                    record_id, value = str(data["record_id"])[:100], str(data["value"])[:1000]
                    STATE["records"][record_id] = value
                    STATE["writes"] += 1
                    return self.reply(200, {"record_id": record_id, "value": value})
                if path == "/chaos":
                    STATE["chaos"] = bool(data["enabled"])
                    STATE["hard"] = bool(data.get("hard", False))
                    STATE["read"] = bool(data.get("read", False))
                    return self.reply(200, {"enabled": STATE["chaos"], "hard": STATE["hard"], "read": STATE["read"]})
                if path == "/reset":
                    STATE.update(records={}, writes=0, chaos=False, hard=False, read=False)
                    return self.reply(200, {"status": "reset"})
        except (KeyError, ValueError, TypeError):
            return self.reply(400, {"error": "bad request"})
        self.reply(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3100)
    port = parser.parse_args().port
    print(f"Record editor at http://127.0.0.1:{port}/records")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
