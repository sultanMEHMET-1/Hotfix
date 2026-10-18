#!/usr/bin/env python3
"""Local inventory desk for repeat-safe write demos, with a click-to-break Chaos control.

State is in memory. Each press of "Break something" applies one more change (POST /chaos
{"next": true}): the save button moves into a dialog (chaos), the Record ID box gets a new id
(input), the saved value's test id is renamed (read), decoy buttons and a search box appear
(hard). At most two changes that break a selector are active at once. A separate "Add sign-in
wall" button (POST /chaos {"break": "login"}) replaces the form with a sign-in wall. POST /chaos {"break": "<name>"}
applies one change deterministically, and the original {"enabled", "hard", "read"} body still
sets the flags directly. GET /state shows records, write count, last save and the active
changes; POST /reset restores the seed inventory and removes every change.
"""

import argparse
from datetime import datetime, timezone
from html import escape
import json
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOCK = threading.Lock()
SEEDS = {"SKU-1042": "19.95", "SKU-1043": "8.50", "SKU-1044": "42.00", "SKU-1045": "6.75",
         "SKU-1046": "11.25", "SKU-1047": "7.95", "SKU-1048": "2.40", "SKU-1049": "3.85",
         "SKU-1050": "12.50", "SKU-1051": "9.90", "SKU-1052": "28.00", "SKU-1053": "5.60"}
SEED_DETAILS = {
    "SKU-1042": {"name": "M8 hex bolt box", "category": "Hardware", "quantity": 24},
    "SKU-1043": {"name": "PTFE thread tape", "category": "Plumbing", "quantity": 4},
    "SKU-1044": {"name": "Nitrile gloves box", "category": "Safety", "quantity": 0},
    "SKU-1045": {"name": "Cable ties pack", "category": "Electrical", "quantity": 60},
    "SKU-1046": {"name": "Utility knife", "category": "Tools", "quantity": 8},
    "SKU-1047": {"name": "Safety glasses", "category": "Safety", "quantity": 3},
    "SKU-1048": {"name": "PVC elbow 25 mm", "category": "Plumbing", "quantity": 35},
    "SKU-1049": {"name": "Electrical tape", "category": "Electrical", "quantity": 12},
    "SKU-1050": {"name": "Shop towels pack", "category": "Supplies", "quantity": 5},
    "SKU-1051": {"name": "Work gloves pair", "category": "Safety", "quantity": 1},
    "SKU-1052": {"name": "Drill bit set", "category": "Tools", "quantity": 9},
    "SKU-1053": {"name": "Steel washers box", "category": "Hardware", "quantity": 4},
}


def fresh_state(generation=0):
    return {"records": dict(SEEDS), "inventory": {key: dict(value) for key, value in SEED_DETAILS.items()},
            "writes": 0, "last_saved": None, "chaos": False, "hard": False, "read": False,
            "input": False, "login": False, "last_break": None, "audit": [], "supplier_note": None, "reset_generation": generation}


STATE = fresh_state()

# key: (state flag, presenter-facing description, whether it breaks a selector)
BREAKS = {
    "button": ("chaos", "The save button moved into a dialog and lost its id.", True),
    "input": ("input", "The Record ID box was given a new id.", True),
    "read": ("read", "The saved value's test id was renamed.", True),
    "decoys": ("hard", "Decoy buttons and a search box appeared.", False),
    "login": ("login", "A sign-in wall replaced the form.", False),
}
MAX_SELECTOR_BREAKS = 2  # a heal fixes one field per agent run and runs at most three, so keep a spare


def applied(state):
    return [key for key, (flag, _, _) in BREAKS.items() if state[flag]]


def next_break(state, rng):
    """The next change a click applies: a random heal-able one, then nothing. The sign-in wall has its own button."""
    active = applied(state)
    pool = [key for key in ("button", "input", "read", "decoys") if key not in active]
    if sum(BREAKS[key][2] for key in active) >= MAX_SELECTOR_BREAKS:
        pool = [key for key in pool if not BREAKS[key][2]]
    return rng.choice(pool) if pool else None


def describe(state):
    last = state["last_break"]
    return {"key": last, "message": BREAKS[last][1]} if last in BREAKS and state[BREAKS[last][0]] else None


def chaos_reply(state):
    return {"enabled": state["chaos"], "hard": state["hard"], "read": state["read"], "input": state["input"],
            "login": state["login"], "broken": applied(state), "last": describe(state), "exhausted": state["login"]}

STYLE = """
:root { color-scheme: light; font-family: Arial, sans-serif; color: #292929; background: #d4d0c8; font-size: 14px; }
body { margin: 0; } * { box-sizing: border-box; }
header { padding: 12px 18px; background: #243b53; color: white; border-bottom: 4px solid #152536; }
header strong { font-size: 18px; } header p { margin: 6px 0 0; color: #e0e7ee; font-size: 13px; }
nav { display: flex; align-items: center; gap: 18px; padding: 7px 18px; border-bottom: 2px groove #eee; background: #d4d0c8; }
nav a { color: #243b53; text-underline-offset: 3px; } #chaos-note { margin-left: auto; color: #555; font-size: 13px; }
button { padding: 5px 12px; border: 2px outset #eee; border-radius: 0; background: #d4d0c8; cursor: pointer; font: inherit; }
button:hover { filter: brightness(.92); } button:disabled { opacity: .65; cursor: wait; }
:focus-visible { outline: 3px solid #b05c00; outline-offset: 3px; } ::selection { background: #f2d28c; color: #292929; }
#break-btn { color: white; background: #9e2929; border-color: #742020; font-weight: bold; }
#login-wall { padding: 12px; border: 2px solid #8b1e1e; background: #fff1f1; } #login-wall h3 { margin: 0 0 6px; }
main { max-width: 1160px; margin: 18px auto; padding: 0 22px; }
h1 { margin: 0 0 8px; font: bold 24px Arial, sans-serif; } h2 { margin: 0 0 10px; font: bold 16px Arial, sans-serif; padding: 7px; background: #243b53; color: white; }
.intro { margin: 0 0 22px; line-height: 1.5; } .layout { display: grid; grid-template-columns: 340px 1fr; gap: 14px; align-items: start; }
.paper { background: #fffef8; border: 2px groove #eee; padding: 12px; min-width: 0; }
.note, .fine-print { color: #555; font-size: 13px; line-height: 1.5; } .note { margin: 0 0 14px; }
label { display: block; margin: 14px 0 6px; font-weight: bold; }
input { display: block; width: 100%; padding: 6px; border: 2px inset #eee; border-radius: 0; font: inherit; caret-color: #243b53; }
#search-slot input { margin-bottom: 12px; } #actions { margin-top: 18px; }
#save-btn, [data-action="save"] { background: #d4d0c8; border-color: #eee; color: #111; font-weight: bold; }
#decoys { display: flex; flex-wrap: wrap; gap: 8px; } #decoys:empty { display: none; }
#result { margin-top: 18px; padding: 12px; background: #e8f5e9; border: 1px solid #356859; overflow-wrap: anywhere; }
[hidden] { display: none !important; } .table-scroll { overflow: auto; max-height: 360px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 8px; border: 1px solid #b6b5af; text-align: left; overflow-wrap: anywhere; }
th { position: sticky; top: 0; background: #deded5; font-size: 13px; } td { font-size: 14px; white-space: pre-wrap; }
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

.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 8px; margin-bottom: 10px; }
.filters label { margin: 0 0 4px; font-size: 13px; } .filters > div { flex: 1; min-width: 120px; }
select, textarea { padding: 6px; border: 2px inset #eee; font: inherit; width: 100%; background: white; }
th button { border: 0; padding: 0; background: transparent; text-decoration: underline; font-weight: bold; text-align: left; }
#inventory table { min-width: 720px; } #inventory th:first-child { min-width: 100px; }
.pager { display: flex; align-items: center; gap: 8px; margin-top: 10px; } .pager span { margin-left: auto; font-size: 12px; }
.warning { padding: 8px 12px; border: 1px solid #8a641c; background: #fff2bd; }
.badge { white-space: nowrap; padding: 2px 4px; border: 1px solid #47704d; background: #e8f5e9; font-size: 12px; }
.badge.low { border-color: #8a641c; background: #fff2bd; } .badge.out { border-color: #853c3c; background: #fce4e4; }
.auxiliary { display: grid; grid-template-columns: 1.5fr 1fr; gap: 14px; margin-top: 14px; }
iframe { display: block; width: 100%; height: 235px; border: 0; } .embedded { padding: 0; background: #fffef8; }
@media (max-width: 860px) { .layout, .auxiliary { grid-template-columns: 1fr; } }
"""

LOGIN = ('<div id="login-wall" role="alert"><h3>Session expired</h3><p>Sign in to continue editing records.</p>'
         '<label for="login-user">Username</label><input id="login-user" autocomplete="off">'
         '<label for="login-pass">Password</label><input id="login-pass" type="password" autocomplete="off">'
         '<button id="login-submit" type="button">Sign in</button></div>')
SEARCH = '<input aria-label="Search records" placeholder="Search records">'
DECOYS = '<button type="button" data-action="draft">Save draft</button><button type="button" id="clear-btn">Clear form</button>'
FORM = """<form id="record-form">
<div><label for="record-id">Record ID</label><input id="record-id" name="record_id" autocomplete="off" required></div>
<div><label for="record-value">New value</label><input id="record-value" name="value" autocomplete="off" required></div>
<div id="decoys">__DECOYS__</div><div id="actions"><button id="save-btn" type="submit">Save record</button></div>
<div id="result" hidden aria-live="polite">Saved <span id="out-record" data-testid="saved-record"></span> = <span id="out-value" data-testid="__VALUE_ID__"></span></div>
</form>"""
SCRIPT = """
(() => {
  const form = document.querySelector('#record-form'), toggle = document.querySelector('#break-btn');
  const restore = document.querySelector('#restore-btn'), loginBtn = document.querySelector('#login-btn');
  const button = document.querySelector('#save-btn'), result = document.querySelector('#result');
  const error = document.querySelector('#action-error'), search = document.querySelector('#inventory-filter');
  const category = document.querySelector('#category-filter'), rendered = new Map();
  let state = null, seen = null, pageNumber = 1, sortKey = 'sku', direction = 1;
  let generation = 0, refreshId = 0, pending = false, modes = __MODES__;
  function text(id, value) { const node = document.getElementById(id); if (node.textContent !== value) node.textContent = value; }
  function update(key, value, draw) {
    const signature = JSON.stringify(value);
    if (rendered.get(key) === signature) return;
    draw(); rendered.set(key, signature);
  }
  function applyModes(next) {
    modes = {chaos: next.chaos, hard: next.hard, read: next.read, input: next.input, login: next.login};
    update('modes', modes, () => {
      document.body.classList.toggle('chaos', modes.chaos);
      text('break-btn', modes.login ? 'Nothing left to break' : 'Break something');
      text('login-btn', modes.login ? 'Sign-in wall up' : 'Add sign-in wall');
      syncButtons();
      const field = form.elements.record_id, label = form.querySelector('label');
      field.id = modes.input ? 'rid' : 'record-id'; label.htmlFor = field.id;
      let wall = document.querySelector('#login-wall');
      if (modes.login && !wall) {
        form.hidden = true; form.insertAdjacentHTML('afterend', document.getElementById('login-template').innerHTML);
      } else if (!modes.login && wall) { wall.remove(); form.hidden = false; }
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
    });
  }
  function anyBroken() { return modes.chaos || modes.hard || modes.read || modes.input || modes.login; }
  function syncButtons() { toggle.disabled = pending || modes.login; loginBtn.disabled = pending || modes.login; restore.disabled = pending || !anyBroken(); }
  function stock(quantity) { return quantity === 0 ? 'Out' : quantity < 5 ? 'Low' : 'In stock'; }
  function matching(record, details) { return `${record} ${details.name}`.toLowerCase().includes(search.value.toLowerCase()); }
  function rows() {
    return Object.entries(state.records).filter(([record]) => matching(record, state.inventory[record]) &&
      (!category.value || state.inventory[record].category === category.value)).sort((a, b) => {
      const value = entry => sortKey === 'sku' ? entry[0] : sortKey === 'value' ? entry[1] :
        sortKey === 'stock' ? (state.inventory[entry[0]].quantity === 0 ? 0 : state.inventory[entry[0]].quantity < 5 ? 1 : 2) : state.inventory[entry[0]][sortKey];
      const left = value(a), right = value(b);
      const numeric = item => String(item).trim() !== '' && Number.isFinite(Number(item));
      let order;
      if (sortKey === 'value' || sortKey === 'quantity' || sortKey === 'stock') {
        order = numeric(left) && numeric(right) ? Number(left) - Number(right) : numeric(left) !== numeric(right) ? (numeric(left) ? -1 : 1) : String(left).localeCompare(String(right));
      } else order = String(left).localeCompare(String(right), undefined, {sensitivity: 'base'});
      return order * direction || a[0].localeCompare(b[0]);
    });
  }
  function inventory() {
    if (!state) return;
    const entries = rows(), pages = Math.max(1, Math.ceil(entries.length / 8));
    pageNumber = Math.max(1, Math.min(pageNumber, pages));
    update('inventory', [state.records, state.inventory, state.last_saved && state.last_saved.record_id,
      search.value, category.value, sortKey, direction, pageNumber], () => {
      const nodes = entries.slice((pageNumber - 1) * 8, pageNumber * 8).map(([record, value]) => {
        const details = state.inventory[record], status = stock(details.quantity), row = document.createElement('tr');
        row.classList.toggle('latest', !!state.last_saved && state.last_saved.record_id === record);
        for (const label of [`SKU: ${record}`, `Item: ${details.name}`, `Category: ${details.category}`, `Value: ${value}`, `Quantity: ${details.quantity}`]) {
          const cell = document.createElement('td'); cell.textContent = label; row.append(cell);
        }
        const cell = document.createElement('td'), badge = document.createElement('span');
        badge.className = `badge ${status === 'Low' ? 'low' : status === 'Out' ? 'out' : ''}`;
        badge.textContent = `Stock: ${status}`; cell.append(badge); row.append(cell); return row;
      });
      document.querySelector('#records-body').replaceChildren(...nodes);
      text('inventory-count', `${entries.length} records / Page ${pageNumber} of ${pages}`);
      document.querySelector('#inventory-empty').hidden = entries.length !== 0;
      document.querySelector('#previous-page').disabled = pageNumber === 1;
      document.querySelector('#next-page').disabled = pageNumber === pages;
      for (const header of document.querySelectorAll('[data-sort]')) header.parentElement.setAttribute('aria-sort',
        header.dataset.sort === sortKey ? (direction === 1 ? 'ascending' : 'descending') : 'none');
    });
  }
  function draw() {
    applyModes(state); inventory();
    text('chaos-note', state.last ? `Last change: ${state.last.message}` : '');
    update('audit', state.audit, () => {
      const nodes = state.audit.map(change => {
        const row = document.createElement('tr');
        for (const value of [`SKU: ${change.record_id}`, `Old price: ${change.old_value === null ? 'New record' : change.old_value}`,
          `New price: ${change.new_value}`, `Time: ${new Date(change.at).toLocaleTimeString()}`]) {
          const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
        }
        return row;
      });
      document.querySelector('#audit-body').replaceChildren(...nodes);
      document.querySelector('#audit-empty').hidden = nodes.length !== 0;
    });
    const low = Object.values(state.inventory).filter(details => details.quantity > 0 && details.quantity < 5).length;
    update('warning', low, () => { text('stock-warning', `Low stock: ${low} inventory records need replenishment.`); document.querySelector('#stock-warning').hidden = low === 0; });
    text('last-saved', `Last saved: ${state.last_saved ? new Date(state.last_saved.at).toLocaleString() : 'No changes yet'}`);
  }
  function reveal(record) {
    const details = state.inventory[record];
    if (!matching(record, details)) search.value = '';
    if (category.value && category.value !== details.category) category.value = '';
    pageNumber = Math.floor(rows().findIndex(entry => entry[0] === record) / 8) + 1;
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
      const next = await request('/state');
      if (started !== generation || id !== refreshId || pending) return;
      const reset = seen !== null && seen.reset_generation !== next.reset_generation;
      state = next;
      if (reset) {
        generation++; search.value = ''; category.value = ''; sortKey = 'sku'; direction = 1; pageNumber = 1;
        document.querySelector('#supplier-note-frame').contentWindow.location.reload();
        result.hidden = true; text('out-record', ''); text('out-value', ''); error.textContent = '';
      } else if (seen !== null && next.writes > seen.writes && next.last_saved) reveal(next.last_saved.record_id);
      if (state.writes === 0 && !result.hidden) { result.hidden = true; text('out-record', ''); text('out-value', ''); }
      seen = {reset_generation: next.reset_generation, writes: next.writes}; draw();
      text('sync-status', 'Inventory connected. Refreshes every second.');
    } catch (_) {
      if (started === generation && id === refreshId && !pending) text('sync-status', 'Inventory sync unavailable. Retrying automatically.');
    }
  }
  for (const control of [search, category]) control.addEventListener(control === search ? 'input' : 'change', () => { pageNumber = 1; inventory(); });
  for (const header of document.querySelectorAll('[data-sort]')) header.addEventListener('click', () => {
    direction = sortKey === header.dataset.sort ? -direction : 1; sortKey = header.dataset.sort; pageNumber = 1; inventory();
  });
  document.querySelector('#previous-page').addEventListener('click', () => { pageNumber--; inventory(); });
  document.querySelector('#next-page').addEventListener('click', () => { pageNumber++; inventory(); });
  async function changeChaos(body) {
    if (pending) return;
    generation++; pending = true; syncButtons(); button.disabled = true; error.textContent = '';
    try {
      const next = await request('/chaos', body);
      applyModes({chaos: next.enabled, hard: next.hard, read: next.read, input: next.input, login: next.login});
    } catch (_) { error.textContent = 'Could not change Chaos Mode. Try again.'; }
    finally { pending = false; syncButtons(); button.disabled = false; }
    await refresh();
  }
  toggle.addEventListener('click', () => changeChaos({next: true}));
  loginBtn.addEventListener('click', () => changeChaos({break: 'login'}));
  restore.addEventListener('click', () => changeChaos({enabled: false, hard: false, read: false, input: false, login: false}));
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (pending) return;
    generation++; pending = true; result.hidden = true; button.disabled = true; syncButtons(); error.textContent = '';
    try {
      const saved = await request('/records', {record_id: form.elements.record_id.value, value: document.querySelector('#record-value').value});
      text('out-record', saved.record_id); text('out-value', saved.value); result.hidden = false;
    } catch (_) { error.textContent = 'Record was not confirmed saved. Check the inventory and try again.'; }
    finally { pending = false; button.disabled = false; syncButtons(); }
    await refresh();
  });
  async function poll() { await refresh(); setTimeout(poll, 1000); }
  applyModes(modes); poll();
})();
"""


def stock(quantity):
    return "Out" if quantity == 0 else "Low" if quantity < 5 else "In stock"


def shell(title, content, script=""):
    links = "".join(f'<a href="/{path}">{label}</a>' for path, label in
                    (("records", "Inventory"), ("orders", "Orders"), ("suppliers", "Suppliers"), ("reports", "Reports")))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title} | Northline Supply</title><style>{STYLE}</style></head><body>'
            '<header><strong>NORTHLINE SUPPLY · INVENTORY CONTROL</strong><p>Internal operations / Administration</p></header>'
            f'<nav aria-label="Administration">{links}</nav><main>{content}'
            '<footer class="fine-print">Northline Supply internal records / Demonstration data</footer></main>'
            f'{script}</body></html>')


def record_row(record, value):
    details = STATE["inventory"][record]
    status = stock(details["quantity"])
    cells = (f"SKU: {record}", f"Item: {details['name']}", f"Category: {details['category']}",
             f"Value: {value}", f"Quantity: {details['quantity']}")
    return ("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in cells)
            + f'<td><span class="badge {status.lower().replace(" ", "-")}">Stock: {status}</span></td></tr>')


def render():
    form = FORM.replace("__DECOYS__", DECOYS if STATE["hard"] else "").replace(
        "__VALUE_ID__", "result-value" if STATE["read"] else "saved-value")
    rows = "".join(record_row(record, STATE["records"][record]) for record in sorted(STATE["records"])[:8])
    headings = "".join(f'<th scope="col"><button type="button" data-sort="{key}">Sort by {label}</button></th>'
                       for key, label in (("sku", "SKU"), ("name", "Item"), ("category", "Category"),
                                          ("value", "Price"), ("quantity", "Quantity"), ("stock", "Stock")))
    categories = "".join(f'<option>{escape(category)}</option>' for category in sorted(
        {details["category"] for details in SEED_DETAILS.values()} | {"Other"}))
    low = sum(0 < details["quantity"] < 5 for details in STATE["inventory"].values())
    content = (f'<h1>Inventory price desk</h1><p id="stock-warning" class="warning" role="status"{ " hidden" if not low else ""}>'
               f'Low stock: {low} inventory records need replenishment.</p><div class="layout">'
               '<section id="editor" class="paper"><h2>Edit a record</h2><p class="note">Enter a SKU and its new price. Other record IDs and text values are also accepted.</p>'
               f'{form}<p id="action-error" role="alert"></p></section>'
               '<section id="inventory" class="paper"><h2>Current inventory</h2><div class="filters">'
               '<div><label for="inventory-filter">Filter inventory</label><input id="inventory-filter" autocomplete="off"></div>'
               f'<div><label for="category-filter">Category</label><select id="category-filter"><option value="">All categories</option>{categories}</select></div></div>'
               f'<div id="search-slot">{SEARCH if STATE["hard"] else ""}</div><div class="table-scroll"><table><thead><tr>{headings}</tr></thead>'
               f'<tbody id="records-body">{rows}</tbody></table></div><p id="inventory-empty" hidden>No records match the current filters.</p>'
               f'<div class="pager"><button id="previous-page" type="button" disabled>Previous page</button><button id="next-page" type="button">Next page</button>'
               f'<span id="inventory-count">{len(STATE["records"])} records / Page 1 of {max(1, (len(STATE["records"]) + 7) // 8)}</span></div>'
               f'<p id="last-saved">Last saved: {escape(STATE["last_saved"]["at"]) if STATE["last_saved"] else "No changes yet"}</p></section></div>'
               '<div class="auxiliary"><section class="paper"><h2>Recent changes</h2><div class="table-scroll"><table><thead><tr><th>SKU</th><th>Old price</th><th>New price</th><th>Time</th></tr></thead>'
               '<tbody id="audit-body"></tbody></table></div><p id="audit-empty">No price changes recorded.</p></section>'
               '<section class="paper"><h2>Supplier notes</h2><iframe id="supplier-note-frame" title="Supplier note" src="/supplier-note"></iframe></section></div>'
               '<p id="sync-status" role="status">Connecting to inventory...</p>')
    modes = json.dumps({key: STATE[key] for key in ("chaos", "hard", "read", "input", "login")})
    scripts = (f'<template id="search-template">{SEARCH}</template><template id="decoy-template">{DECOYS}</template><template id="login-template">{LOGIN}</template>'
               f'<script>{SCRIPT.replace("__MODES__", modes)}</script>')
    page = shell("Inventory", content, scripts)
    return page.replace('</nav>', '<span id="chaos-note" role="status"></span><button id="break-btn" type="button">Break something</button>'
                       '<button id="login-btn" type="button">Add sign-in wall</button><button id="restore-btn" type="button" disabled>Restore site</button></nav>', 1)


STATIC_PAGES = {
    "orders": ("Open orders", "<tr><td>PO-2048</td><td>Fastener replenishment</td><td>Awaiting delivery</td></tr><tr><td>PO-2049</td><td>Safety equipment</td><td>Approved</td></tr>"),
    "suppliers": ("Supplier directory", "<tr><td>SUP-017</td><td>Allied Industrial</td><td>Hardware and tools</td></tr><tr><td>SUP-024</td><td>West Coast Safety</td><td>Protective equipment</td></tr>"),
    "reports": ("Operations reports", "<tr><td>INV-01</td><td>Inventory valuation</td><td>Monthly</td></tr><tr><td>STK-02</td><td>Replenishment review</td><td>Weekly</td></tr>"),
}


def note_page():
    note = STATE["supplier_note"]
    confirmation = escape(f"Note attached for {note['supplier']}: {note['note']}") if note else "No supplier note attached."
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{STYLE}</style></head><body class="embedded">'
            '<form id="supplier-note-form"><label for="supplier-reference">Supplier reference</label><input id="supplier-reference" maxlength="100" required>'
            '<label for="supplier-note">Supplier note</label><input id="supplier-note" maxlength="1000" required>'
            '<button id="note-submit" type="submit">Attach note</button></form>'
            f'<p id="note-result" role="status">{confirmation}</p><script>'
            "document.querySelector('form').addEventListener('submit', async event => { event.preventDefault(); const button = document.querySelector('#note-submit'); button.disabled = true;"
            "try { const response = await fetch('/supplier-note', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({supplier:document.querySelector('#supplier-reference').value,note:document.querySelector('#supplier-note').value})});"
            "if (!response.ok) throw new Error('Request failed'); const saved = await response.json(); document.querySelector('#note-result').textContent = `Note attached for ${saved.supplier}: ${saved.note}`;"
            "} catch (_) { document.querySelector('#note-result').textContent = 'Note was not confirmed saved. Try again.'; } finally {button.disabled = false;} });"
            '</script></body></html>')


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
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("body must be an object")
        return data

    def do_GET(self):
        path = urlsplit(self.path).path
        with LOCK:
            if path in {"/", "/records"}:
                return self.reply(200, render(), "text/html")
            if path == "/state":
                return self.reply(200, {**STATE, "broken": applied(STATE), "last": describe(STATE)})
            if path == "/supplier-note":
                return self.reply(200, note_page(), "text/html")
            if path[1:] in STATIC_PAGES:
                title, rows = STATIC_PAGES[path[1:]]
                return self.reply(200, shell(title, f'<h1>{title}</h1><section class="paper"><table><thead><tr><th>Reference</th><th>Description</th><th>Status / Schedule</th></tr></thead><tbody>{rows}</tbody></table><p><a href="/records">Return to inventory</a></p></section>'), "text/html")
        self.reply(200 if path == "/healthz" else 404, {"status": "ok"} if path == "/healthz" else {"error": "not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            data = self.body()
            with LOCK:
                if path == "/records":
                    record_id, value = str(data["record_id"])[:100], str(data["value"])[:1000]
                    at = datetime.now(timezone.utc).isoformat()
                    STATE["audit"].insert(0, {"record_id": record_id, "old_value": STATE["records"].get(record_id), "new_value": value, "at": at})
                    del STATE["audit"][5:]
                    STATE["records"][record_id] = value
                    STATE["inventory"].setdefault(record_id, {"name": "Custom record", "category": "Other", "quantity": 0})
                    STATE["writes"] += 1
                    STATE["last_saved"] = {"record_id": record_id, "value": value, "at": at}
                    return self.reply(200, {"record_id": record_id, "value": value})
                if path == "/supplier-note":
                    supplier, note = str(data["supplier"])[:100], str(data["note"])[:1000]
                    if not supplier or not note:
                        raise ValueError("empty note")
                    STATE["supplier_note"] = {"supplier": supplier, "note": note}
                    return self.reply(200, STATE["supplier_note"])
                if path == "/chaos":
                    if "break" in data or data.get("next"):
                        key = data["break"] if "break" in data else next_break(STATE, random)
                        if key is not None:
                            STATE[BREAKS[key][0]] = True
                            STATE["last_break"] = key
                    else:
                        enabled = bool(data["enabled"])
                        for flag, _, _ in BREAKS.values():
                            STATE[flag] = enabled if flag == "chaos" else bool(data.get(flag, False))
                        STATE["last_break"] = None
                    return self.reply(200, chaos_reply(STATE))
                if path == "/reset":
                    generation = STATE["reset_generation"] + 1
                    STATE.clear()
                    STATE.update(fresh_state(generation))
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
