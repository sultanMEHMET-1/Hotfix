#!/usr/bin/env python3
"""Local inventory desk for repeat-safe write demos, with shared Chaos Mode.

State is in memory. hard=true adds a search box, Save draft and Clear form decoys.
read=true renames the saved value's test id without breaking the save. GET /state
shows records, write count and last save; POST /reset restores the seed inventory.
"""

import argparse
from datetime import datetime, timezone
from html import escape
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOCK = threading.Lock()
SEEDS = {"SKU-1042": "19.95", "SKU-1043": "8.50", "SKU-1044": "42.00"}
STATE = {"records": dict(SEEDS), "writes": 0, "last_saved": None, "chaos": False, "hard": False, "read": False}

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Inventory Price Desk</title>
<style>
:root { color-scheme: light; font-family: Arial, sans-serif; color: #292929; background: #e7e3d8; }
body { margin: 0; } * { box-sizing: border-box; }
header { padding: 18px 26px; background: #243b53; color: white; border-bottom: 4px solid #152536; }
header strong { font-size: 20px; } header p { margin: 6px 0 0; color: #e0e7ee; font-size: 13px; }
nav { display: flex; align-items: center; gap: 22px; padding: 10px 26px; border-bottom: 1px solid #aaa; background: #fffef8; }
nav a { color: #243b53; text-underline-offset: 3px; } nav button { margin-left: auto; }
button { padding: 9px 14px; border: 1px solid #666; border-radius: 2px; cursor: pointer; font: inherit; }
button:hover { filter: brightness(.92); } button:disabled { opacity: .65; cursor: wait; }
:focus-visible { outline: 3px solid #b05c00; outline-offset: 3px; } ::selection { background: #f2d28c; color: #292929; }
#chaos-toggle { color: white; background: #9e2929; border-color: #742020; font-weight: bold; }
main { max-width: 1060px; margin: 28px auto; padding: 0 22px; }
h1 { margin: 0 0 8px; font: bold 30px Georgia, serif; } h2 { margin: 0 0 10px; font: bold 22px Georgia, serif; }
.intro { margin: 0 0 22px; line-height: 1.5; } .layout { display: grid; grid-template-columns: 1fr 1.15fr; gap: 22px; align-items: start; }
.paper { background: #fffef8; border: 1px solid #999; padding: 22px; min-width: 0; }
.note, .fine-print { color: #555; font-size: 13px; line-height: 1.5; } .note { margin: 0 0 14px; }
label { display: block; margin: 14px 0 6px; font-weight: bold; }
input { display: block; width: 100%; padding: 9px; border: 1px solid #777; border-radius: 2px; font: inherit; caret-color: #243b53; }
#search-slot input { margin-bottom: 12px; } #actions { margin-top: 18px; }
#save-btn, [data-action="save"] { background: #2e7138; border-color: #24592c; color: white; font-weight: bold; }
#decoys { display: flex; flex-wrap: wrap; gap: 8px; } #decoys:empty { display: none; }
#result { margin-top: 18px; padding: 12px; background: #e8f5e9; border: 1px solid #356859; overflow-wrap: anywhere; }
[hidden] { display: none !important; } .table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 12px 10px; border: 1px solid #b6b5af; text-align: left; overflow-wrap: anywhere; }
th { background: #deded5; font-size: 13px; } td { font-size: 15px; white-space: pre-wrap; }
tbody tr:nth-child(even) { background: #f2f0e8; } tr.latest { background: #e8f5e9 !important; }
#last-saved { margin: 14px 0 0; font-size: 13px; } #sync-status, #action-error { min-height: 20px; font-size: 13px; }
#action-error { color: #8b1e1e; } footer { margin: 22px 0; padding-top: 12px; border-top: 1px solid #aaa; }
.chaos header { background: #4e3833; } .chaos .layout { grid-template-columns: 1fr; gap: 16px; }
.chaos #inventory { grid-row: 1; } .chaos #editor { background: #f5eee4; border: 2px solid #805744; }
.chaos #record-form { display: grid; grid-template-columns: 1fr 1fr; gap: 0 22px; }
.chaos #actions, .chaos #decoys, .chaos #result { grid-column: 1 / -1; }
#chaos-modal { border: 2px solid #8b1e1e; background: #fff1f1; padding: 12px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
#chaos-modal::before { content: "Price change authorization"; color: #742020; font-weight: bold; }
@media (max-width: 680px) { header, nav { padding: 14px; } nav { gap: 14px; flex-wrap: wrap; }
main { padding: 0 14px; margin-top: 22px; } .layout, .chaos #record-form { grid-template-columns: 1fr; }
.paper { padding: 18px; } h1 { font-size: 26px; } #chaos-modal { align-items: start; flex-direction: column; } }
</style></head><body>
<header><strong>NORTHLINE SUPPLY · INVENTORY CONTROL</strong><p>Internal operations / Price maintenance</p></header>
<nav aria-label="Page sections"><a href="#editor">Edit record</a><a href="#inventory">Current inventory</a>
<button id="chaos-toggle" type="button" aria-pressed="false">Chaos Mode: OFF</button></nav>
<main><h1>Inventory price desk</h1><p class="intro">Update an inventory record, then check the current value below. Demonstration inventory only.</p>
<div class="layout"><section id="editor" class="paper" aria-labelledby="edit-title"><h2 id="edit-title">Edit a record</h2>
<p class="note">Enter a SKU and its new price. Other record IDs and text values are also accepted.</p>
<form id="record-form">
<div><label for="record-id">Record ID</label><input id="record-id" name="record_id" autocomplete="off" required></div>
<div><label for="record-value">New value</label><input id="record-value" name="value" autocomplete="off" required></div>
<div id="decoys">__DECOYS__</div><div id="actions"><button id="save-btn" type="submit">Save record</button></div>
<div id="result" hidden aria-live="polite">Saved <span id="out-record" data-testid="saved-record"></span> = <span id="out-value" data-testid="__VALUE_ID__"></span></div>
</form><p id="action-error" role="alert"></p></section>
<section id="inventory" class="paper" aria-labelledby="inventory-title"><h2 id="inventory-title">Current inventory</h2>
<p class="note">Shared records. Changes from other sessions appear automatically.</p><div id="search-slot">__SEARCH__</div>
<div class="table-scroll"><table><thead><tr><th scope="col">Record / SKU</th><th scope="col">Current value</th></tr></thead><tbody id="records-body">__ROWS__</tbody></table></div>
<p id="last-saved">Last saved: __LAST_SAVED__</p></section></div>
<p id="sync-status" role="status">Connecting to inventory...</p>
<footer class="fine-print">Local demonstration system. Records are held in memory; reset restores the sample inventory.</footer></main>
<template id="search-template">__SEARCH_TEMPLATE__</template><template id="decoy-template">__DECOY_TEMPLATE__</template>
<script>
(() => {
  const form = document.querySelector('#record-form'), toggle = document.querySelector('#chaos-toggle');
  const button = document.querySelector('#save-btn'), result = document.querySelector('#result');
  const error = document.querySelector('#action-error'), sync = document.querySelector('#sync-status');
  let modes = __MODES__, generation = 0, refreshId = 0, pending = false;
  function applyModes(state) {
    modes = {chaos: state.chaos, hard: state.hard, read: state.read};
    document.body.classList.toggle('chaos', modes.chaos);
    toggle.textContent = `Chaos Mode: ${modes.chaos ? 'ON' : 'OFF'}`;
    toggle.setAttribute('aria-pressed', String(modes.chaos));
    document.querySelector('#out-value').setAttribute('data-testid', modes.read ? 'result-value' : 'saved-value');
    for (const [slot, template] of [['search-slot', 'search-template'], ['decoys', 'decoy-template']]) {
      const container = document.getElementById(slot);
      if (modes.hard && !container.firstChild) container.append(document.getElementById(template).content.cloneNode(true));
      if (!modes.hard) container.replaceChildren();
    }
    let dialog = document.querySelector('#chaos-modal');
    if (modes.chaos && !dialog) {
      button.removeAttribute('id'); button.setAttribute('data-action', 'save');
      dialog = document.createElement('div'); dialog.id = 'chaos-modal';
      dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-label', 'Save record dialog');
      button.replaceWith(dialog); dialog.append(button);
    } else if (!modes.chaos && dialog) {
      button.id = 'save-btn'; button.removeAttribute('data-action'); dialog.replaceWith(button);
    }
  }
  async function request(path, body) {
    const response = await fetch(path, body === undefined ? {} : {
      method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body)});
    if (!response.ok) throw new Error('Request failed');
    return response.json();
  }
  async function refresh() {
    if (pending) return;
    const started = generation, id = ++refreshId;
    try {
      const state = await request('/state');
      if (started !== generation || id !== refreshId || pending) return;
      applyModes(state);
      const rows = Object.entries(state.records).map(([record, value]) => {
        const row = document.createElement('tr');
        row.classList.toggle('latest', state.last_saved !== null && state.last_saved.record_id === record);
        for (const text of [`SKU: ${record}`, `Value: ${value}`]) {
          const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
        }
        return row;
      });
      document.querySelector('#records-body').replaceChildren(...rows);
      document.querySelector('#last-saved').textContent = `Last saved: ${state.last_saved ? new Date(state.last_saved.at).toLocaleString() : 'No changes yet'}`;
      if (state.writes === 0) { result.hidden = true; document.querySelector('#out-record').textContent = ''; document.querySelector('#out-value').textContent = ''; }
      sync.textContent = 'Inventory connected. Refreshes every second.';
    } catch (_) {
      if (started === generation && id === refreshId && !pending) sync.textContent = 'Inventory sync unavailable. Retrying automatically.';
    }
  }
  toggle.addEventListener('click', async () => {
    if (pending) return;
    generation++; pending = true; toggle.disabled = true; button.disabled = true; error.textContent = '';
    try {
      const state = await request('/chaos', {enabled: !modes.chaos, hard: modes.hard, read: modes.read});
      applyModes({chaos: state.enabled, hard: state.hard, read: state.read});
    } catch (_) { error.textContent = 'Could not change Chaos Mode. Try again.'; }
    finally { pending = false; toggle.disabled = false; button.disabled = false; }
    await refresh();
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (pending) return;
    generation++; pending = true; result.hidden = true; button.disabled = true; toggle.disabled = true; error.textContent = '';
    try {
      const saved = await request('/records', {record_id: document.querySelector('#record-id').value, value: document.querySelector('#record-value').value});
      document.querySelector('#out-record').textContent = saved.record_id;
      document.querySelector('#out-value').textContent = saved.value;
      result.hidden = false;
    } catch (_) { error.textContent = 'Record was not confirmed saved. Check the inventory and try again.'; }
    finally { pending = false; button.disabled = false; toggle.disabled = false; }
    await refresh();
  });
  async function poll() { await refresh(); setTimeout(poll, 1000); }
  applyModes(modes); poll();
})();
</script></body></html>"""

SEARCH = '<input aria-label="Search records" placeholder="Search records">'
DECOYS = '<button type="button" data-action="draft">Save draft</button><button type="button" id="clear-btn">Clear form</button>'


def render():
    rows = "".join(f"<tr><td>SKU: {escape(record)}</td><td>Value: {escape(value)}</td></tr>"
                   for record, value in STATE["records"].items())
    replacements = {"__MODES__": json.dumps({key: STATE[key] for key in ("chaos", "hard", "read")}),
                    "__VALUE_ID__": "result-value" if STATE["read"] else "saved-value",
                    "__SEARCH__": SEARCH if STATE["hard"] else "", "__DECOYS__": DECOYS if STATE["hard"] else "",
                    "__SEARCH_TEMPLATE__": SEARCH, "__DECOY_TEMPLATE__": DECOYS, "__ROWS__": rows,
                    "__LAST_SAVED__": escape(STATE["last_saved"]["at"]) if STATE["last_saved"] else "No changes yet"}
    # One pass keeps record text that resembles a template token literal.
    return re.sub(r"__[A-Z_]+__", lambda match: replacements[match[0]], PAGE)


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
                    STATE["last_saved"] = {"record_id": record_id, "value": value, "at": datetime.now(timezone.utc).isoformat()}
                    return self.reply(200, {"record_id": record_id, "value": value})
                if path == "/chaos":
                    STATE["chaos"] = bool(data["enabled"])
                    STATE["hard"] = bool(data.get("hard", False))
                    STATE["read"] = bool(data.get("read", False))
                    return self.reply(200, {"enabled": STATE["chaos"], "hard": STATE["hard"], "read": STATE["read"]})
                if path == "/reset":
                    STATE.update(records=dict(SEEDS), writes=0, last_saved=None, chaos=False, hard=False, read=False)
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
    print(f"Inventory desk at http://127.0.0.1:{port}/records")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
