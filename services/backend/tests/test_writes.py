"""Write workflows: the local-only guard, and healing a save button on the local sandbox site."""

from dataclasses import replace
import json
import os
import random
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

import httpx
from fastapi.testclient import TestClient

from contracts.api_types import HealEvidence
from services.backend.config import write_allowed
from services.backend.healer import Candidate, read_selector_expression
from services.backend.sandbox.records_site import SEEDS, SEED_DETAILS, stock
from services.backend.main import create_app
from services.backend.tests.test_m1 import CORRECT
from services.backend.tests.support import make_root
from services.backend.tests.test_m2 import M2Harness

ROOT = Path(__file__).resolve().parents[3]
SAVE = 'button[data-action="save"]'

RECORD_UPDATE = json.loads((ROOT / "contracts/workflows/record-update.json").read_text())


class SeedInventoryTests(unittest.TestCase):
    def test_twelve_prices_and_stock_boundaries(self):
        self.assertEqual(set(SEEDS), {f"SKU-{number}" for number in range(1042, 1054)})
        self.assertEqual({key: SEEDS[key] for key in ("SKU-1042", "SKU-1043", "SKU-1044")},
                         {"SKU-1042": "19.95", "SKU-1043": "8.50", "SKU-1044": "42.00"})
        self.assertEqual(set(SEED_DETAILS), set(SEEDS))
        for value in SEEDS.values():
            self.assertRegex(value, r"^\d+\.\d{2}$")
        for quantity, expected in ((0, "Out"), (1, "Low"), (4, "Low"), (5, "In stock")):
            self.assertEqual(stock(quantity), expected)
        self.assertTrue({0, 1, 4, 5}.issubset({item["quantity"] for item in SEED_DETAILS.values()}))


class BreakSequenceTests(unittest.TestCase):
    def test_every_click_breaks_something_new_and_never_runs_out_or_adds_the_login_wall(self):
        from services.backend.sandbox import records_site as site
        state = site.fresh_state()
        rng = random.Random(7)
        seen = set()
        for _ in range(200):
            key, variant = site.next_break(state, rng)
            self.assertNotEqual(key, "login")
            if key in site.VARIANTS:
                self.assertNotEqual(state["variants"].get(key), variant)
                state["variants"][key] = variant
            state[site.BREAKS[key][0]] = True
            seen.add((key, variant))
            self.assertLessEqual(sum(site.BREAKS[k][2] for k in site.applied(state)), site.MAX_SELECTOR_BREAKS)
        for key in (k for k in site.applied(state) if k in site.VARIANTS):
            self.assertEqual({n for k, n in seen if k == key}, set(range(len(site.VARIANTS[key]))))

    def test_the_selector_cap_is_what_keeps_a_spare_agent_run(self):
        from services.backend.sandbox import records_site as site
        state = site.fresh_state()
        state["chaos"] = state["input"] = True
        state["variants"] = {"button": 0, "input": 0}
        for seed in range(100):
            key, _ = site.next_break(state, random.Random(seed))
            self.assertIn(key, {"button", "input", "decoys"})


class WriteGuardTests(unittest.TestCase):
    def test_only_loopback_and_allowlisted_hosts_may_be_written_to(self):
        for url in ("http://127.0.0.1:3100/records", "http://localhost/x", "http://[::1]:8/x"):
            self.assertTrue(write_allowed(url), url)
        for url in ("https://portal.example.gov/x", "http://127.0.0.1.evil.com/x", "http://127.0.0.1@evil.com/x", "not a url"):
            self.assertFalse(write_allowed(url), url)
        self.assertTrue(write_allowed("https://staging.corp.test/x", ("staging.corp.test",)))


class WriteRefusalTests(M2Harness):
    async def served(self, target_url, hosts=()):
        (self.root / "contracts/workflows/sample-lookup.json").write_text(json.dumps({**self.definition, "mutates": True}))
        self.path.write_text(json.dumps({**self.baseline, "target_url": target_url,
                                         "fields": {"submit_button": CORRECT, "input_reference": "#reference"}}))
        app = create_app(replace(self.settings, write_hosts=hosts))
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        self.addAsyncCleanup(lifespan.__aexit__, None, None, None)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://backend.test")
        self.addAsyncCleanup(client.aclose)
        return (await client.post("/api/v1/run-workflow", json={"workflow": "sample-lookup", "params": {"record_id": "r"}})).json()

    async def test_public_site_is_refused_before_the_runner_starts(self):
        payload = await self.served("http://portal.test/lookup")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["code"], "write_not_allowed")
        self.assertFalse(payload["recovery_attempted"])
        self.assertFalse((self.root / "runs").exists(), "the runner must not have been started")

    async def test_loopback_and_allowlisted_sites_run(self):
        self.assertEqual((await self.served("http://127.0.0.1:3100/records"))["status"], "success")
        self.assertEqual((await self.served("http://portal.test/lookup", ("portal.test",)))["status"], "success")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(os.getenv("MENDER_BROWSER_TEST") == "1", "Set MENDER_BROWSER_TEST=1 (needs Chrome and playwright)")
class SandboxSiteTests(unittest.TestCase):
    def setUp(self):
        port = free_port()
        self.site = f"http://127.0.0.1:{port}"
        server = subprocess.Popen([sys.executable, str(ROOT / "services/backend/sandbox/records_site.py"), "--port", str(port)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(server.wait)
        self.addCleanup(server.terminate)
        for _ in range(50):
            try:
                urlopen(f"{self.site}/healthz", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = {**json.loads((ROOT / "contracts/selectors/record-update.json").read_text()),
                         "target_url": f"{self.site}/records"}
        self.path = make_root(self.root, "record-update", RECORD_UPDATE, self.baseline)
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        executable = os.getenv("MENDER_BROWSER_EXECUTABLE") or (chrome if Path(chrome).is_file() else "")
        env = patch.dict(os.environ, {"SENTRY_DSN": "", "MENDER_BROWSER_EXECUTABLE": executable, "ANONYMIZED_TELEMETRY": "false"})
        env.start()
        self.addCleanup(env.stop)
        from services.backend.config import Settings
        self.settings = Settings(root=self.root, runner_script=ROOT / "services/runner/execute.py",
                                 runner_python=str(ROOT / ".venv/bin/python"), runner_timeout=30,
                                 browser_executable=executable or None)
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def post(self, path, body):
        return json.load(urlopen(Request(f"{self.site}{path}", json.dumps(body).encode(), method="POST"), timeout=3))

    def state(self):
        return json.load(urlopen(f"{self.site}/state", timeout=3))

    def request(self, record_id="rec-1", value="hello"):
        return self.client.post("/api/v1/run-workflow",
                                json={"workflow": "record-update", "params": {"record_id": record_id, "value": value}}).json()

    def page(self):
        from playwright.sync_api import expect, sync_playwright
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(executable_path=self.settings.browser_executable)
        self.addCleanup(browser.close)
        self.expect = expect
        page = browser.new_page()
        page.goto(f"{self.site}/records")
        self.expect(page.locator("#sync-status")).to_contain_text("Inventory connected")
        return page

    def save(self, page, record, value):
        page.locator("#record-id").fill(record)
        page.locator("#record-value").fill(value)
        page.get_by_role("button", name="Save record", exact=True).click()
        self.expect(page.locator("#result")).to_be_visible()
        self.expect(page.locator("#out-value")).to_have_text(value)

    def test_table_updates_inserts_and_observes_runner_writes_without_losing_input(self):
        page = self.page()
        self.expect(page.locator("#records-body tr")).to_have_count(8)
        self.save(page, "SKU-1042", "21.00")
        self.expect(page.locator("#records-body")).to_contain_text("Value: 21.00")
        self.expect(page.locator("#records-body tr")).to_have_count(8)
        self.save(page, "new-record", "hello")
        self.save(page, "new-record", "hello")
        self.assertEqual(len(self.state()["records"]), len(SEEDS) + 1)
        self.expect(page.locator("#records-body tr")).to_have_count(8)
        self.assertEqual(self.state()["writes"], 3)
        page.reload()
        self.expect(page.locator("#records-body")).to_contain_text("Value: hello")
        self.expect(page.locator("#result")).to_be_hidden()
        page.locator("#record-id").fill("unfinished")
        page.locator("#record-value").fill("keep typing")
        payload = self.request("runner-record", "runner-value")
        self.assertEqual(payload["status"], "success", payload)
        self.expect(page.locator("#records-body")).to_contain_text("Value: runner-value")
        self.expect(page.locator("#record-id")).to_have_value("unfinished")
        self.expect(page.locator("#record-value")).to_have_value("keep typing")
        self.expect(page.locator("#result")).to_be_hidden()
        self.expect(page.locator("#last-saved")).not_to_contain_text("No changes yet")
        self.assertEqual(self.state()["last_saved"]["value"], "runner-value")

    def test_break_button_persists_and_hard_decoys_do_not_write(self):
        page = self.page()
        self.post("/chaos", {"break": "button"})
        self.expect(page.locator("#save-btn")).to_have_count(0)
        self.expect(page.locator('#chaos-modal button[data-action="save"]')).to_have_count(1)
        self.assertTrue(self.state()["chaos"])
        page.reload()
        self.expect(page.locator("#chaos-modal")).to_be_visible()
        self.post("/chaos", {"enabled": True, "hard": True, "read": True})
        self.expect(page.get_by_role("textbox", name="Search records")).to_be_visible()
        self.expect(page.locator("#out-value")).to_have_attribute("data-testid", "result-value")
        page.get_by_role("button", name="Save draft", exact=True).click()
        page.get_by_role("button", name="Clear form", exact=True).click()
        self.assertEqual(self.state()["writes"], 0)
        self.post("/chaos", {"enabled": False, "hard": True, "read": True})
        self.expect(page.locator("#save-btn")).to_be_visible()
        self.expect(page.locator("#chaos-modal")).to_have_count(0)
        self.assertEqual({key: self.state()[key] for key in ("chaos", "hard", "read")},
                         {"chaos": False, "hard": True, "read": True})
        page.reload()
        self.expect(page.locator("#save-btn")).to_be_visible()
        self.expect(page.locator("#out-value")).to_have_attribute("data-testid", "result-value")

    def test_bodies_that_are_not_objects_get_a_400_and_a_flag_restored_by_a_legacy_reset_stays_off(self):
        from urllib.error import HTTPError
        for path in ("/chaos", "/records", "/supplier-note"):
            for body in (b"[]", b'"x"', b"5", b"{not json"):
                with self.subTest(path=path, body=body), self.assertRaises(HTTPError) as caught:
                    urlopen(Request(f"{self.site}{path}", body, method="POST"), timeout=3)
                self.assertEqual(caught.exception.code, 400)
        self.post("/chaos", {"break": "input"})
        self.post("/chaos", {"break": "login"})
        self.post("/chaos", {"enabled": False})
        self.assertEqual(self.state()["broken"], [])

    def test_the_break_button_applies_one_more_change_per_click_and_restore_undoes_them(self):
        page = self.page()
        self.expect(page.locator("#restore-btn")).to_be_disabled()
        for expected in (1, 2):
            page.locator("#break-btn").click()
            self.expect(page.locator("#chaos-note")).to_contain_text("Last change:")
            self.assertEqual(len(self.state()["broken"]), expected)
        page.locator("#restore-btn").click()
        self.expect(page.locator("#restore-btn")).to_be_disabled()
        self.assertEqual(self.state()["broken"], [])
        for field, selector in self.baseline["fields"].items():
            self.expect(page.locator(selector)).to_have_count(1)

    def test_a_broken_record_id_keeps_its_label_and_one_unique_attribute(self):
        page = self.page()
        self.post("/chaos", {"break": "input"})
        self.expect(page.locator("#record-id")).to_have_count(0)
        self.expect(page.get_by_role("textbox", name="Record ID", exact=True)).to_have_count(1)
        self.expect(page.locator('input[name="record_id"]')).to_have_count(1)
        page.locator('input[name="record_id"]').fill("SKU-1042")
        page.locator("#record-value").fill("77.77")
        page.get_by_role("button", name="Save record", exact=True).click()
        self.expect(page.locator("#out-value")).to_have_text("77.77")
        self.assertEqual(self.state()["records"]["SKU-1042"], "77.77")
        self.post("/chaos", {"enabled": False})
        self.expect(page.locator("#record-id")).to_have_count(1)

    def test_the_login_wall_hides_the_price_form_and_reset_removes_it(self):
        page = self.page()
        self.post("/chaos", {"break": "login"})
        self.expect(page.locator("#login-wall")).to_be_visible()
        self.expect(page.locator("#record-form")).to_be_hidden()
        self.expect(page.locator("#break-btn")).to_be_disabled()
        self.assertEqual(page.locator("form").count(), 1)
        self.post("/reset", {})
        self.expect(page.locator("#login-wall")).to_have_count(0)
        self.expect(page.locator("#record-form")).to_be_visible()

    def test_reset_restores_seeds_and_clears_metadata_modes_and_receipt(self):
        page = self.page()
        self.save(page, "SKU-1042", "changed")
        self.post("/records", {"record_id": "extra", "value": "x"})
        self.post("/chaos", {"enabled": True, "hard": True, "read": True})
        self.expect(page.locator("#chaos-modal")).to_be_visible()
        self.post("/reset", {})
        self.expect(page.locator("#last-saved")).to_have_text("Last saved: No changes yet")
        self.expect(page.locator("#records-body tr")).to_have_count(8)
        self.expect(page.locator("#records-body")).to_contain_text("Value: 19.95")
        self.expect(page.locator("#result")).to_be_hidden()
        self.expect(page.locator("#save-btn")).to_be_visible()
        self.expect(page.get_by_role("textbox", name="Search records")).to_have_count(0)
        state = self.state()
        self.assertEqual(state["records"], SEEDS)
        self.assertEqual(state["inventory"], SEED_DETAILS)
        self.assertEqual((state["writes"], state["last_saved"], state["audit"], state["supplier_note"]), (0, None, [], None))
        self.assertEqual((state["chaos"], state["hard"], state["read"], state["reset_generation"]), (False, False, False, 1))

    def test_literal_values_remain_safe_and_the_real_read_probe_is_unique(self):
        page = self.page()
        record, value = 'référence<"&', '<img src=x onerror=alert(1)> __MODES__ café'
        self.save(page, record, value)
        for text, testid in ((record, "saved-record"), (value, "saved-value")):
            found = page.evaluate(read_selector_expression((text,)))
            self.assertEqual((found["count"], found["selector"]), (1, f'span[data-testid="{testid}"]'))
        self.assertEqual(page.locator("img").count(), 0)
        self.assertFalse(page.evaluate("texts => [...document.querySelectorAll('*')].some(node => [...node.attributes].some(attr => texts.some(text => attr.value.includes(text))))", [record, value]))
        self.assertNotIn(value, page.locator("script").inner_text())
        page.reload()
        self.expect(page.locator("#sync-status")).to_contain_text("Inventory connected")
        page.get_by_label("Filter inventory").fill(record)
        self.expect(page.locator("#records-body")).to_contain_text(value)
        self.assertEqual(page.locator("img").count(), 0)
        self.post("/chaos", {"enabled": False, "read": True})
        self.expect(page.locator("#out-value")).to_have_attribute("data-testid", "result-value")
        self.save(page, record, value)
        self.assertEqual(page.evaluate(read_selector_expression((value,)))["selector"],
                         'span[data-testid="result-value"]')

    def test_an_old_state_response_cannot_undo_a_local_save(self):
        page = self.page()
        held = []
        page.route("**/state", lambda route: held.append((route, self.state())))
        page.wait_for_timeout(1200)
        self.assertTrue(held)
        self.save(page, "SKU-1042", "new-price")
        page.wait_for_timeout(100)
        self.assertGreaterEqual(len(held), 2)
        held[-1][0].fulfill(json=held[-1][1])
        self.expect(page.locator("#records-body")).to_contain_text("Value: new-price")
        held[0][0].fulfill(json=held[0][1])
        page.wait_for_timeout(100)
        self.expect(page.locator("#records-body")).to_contain_text("Value: new-price")
        self.expect(page.locator("#result")).to_be_visible()
        page.unroute("**/state")

    def test_receipt_is_hidden_until_each_save_is_acknowledged(self):
        page = self.page()
        self.save(page, "SKU-1042", "first-value")
        held = []
        page.route("**/records", lambda route: held.append(route))
        page.locator("#record-value").fill("second-value")
        page.locator("#save-btn").click()
        self.expect(page.locator("#result")).to_be_hidden()
        page.wait_for_timeout(100)
        self.assertEqual(len(held), 1)
        saved = self.post("/records", {"record_id": "SKU-1042", "value": "second-value"})
        held[0].fulfill(json=saved)
        self.expect(page.locator("#result")).to_be_visible()
        self.expect(page.locator("#out-value")).to_have_text("second-value")

    def test_network_errors_are_visible_and_do_not_claim_a_save(self):
        page = self.page()
        page.route("**/state", lambda route: route.fulfill(status=503, json={}))
        self.expect(page.locator("#sync-status")).to_contain_text("sync unavailable")
        page.unroute("**/state")
        self.expect(page.locator("#sync-status")).to_contain_text("Inventory connected")
        page.route("**/chaos", lambda route: route.fulfill(status=503, json={}))
        page.locator("#break-btn").click()
        self.expect(page.locator("#action-error")).to_contain_text("Could not change Chaos Mode")
        self.expect(page.locator("#break-btn")).to_be_enabled()
        page.route("**/records", lambda route: route.fulfill(status=503, json={}))
        page.locator("#record-id").fill("SKU-1042")
        page.locator("#record-value").fill("not-saved")
        page.locator("#save-btn").click()
        self.expect(page.locator("#action-error")).to_contain_text("not confirmed saved")
        self.expect(page.locator("#result")).to_be_hidden()
        self.assertEqual(self.state()["writes"], 0)

    def test_failure_form_stays_stable_when_shared_inventory_changes(self):
        page = self.page()
        self.post("/chaos", {"enabled": True, "hard": True})
        self.expect(page.locator("#chaos-modal")).to_be_visible()
        before = page.locator("form").evaluate("node => node.outerHTML")
        self.post("/records", {"record_id": "outside", "value": "outside-value"})
        self.expect(page.locator("#records-body")).to_contain_text("outside-value")
        self.assertEqual(page.locator("form").evaluate("node => node.outerHTML"), before)
        self.assertLess(len(before), 1500)
        self.assertNotIn("Last saved", before)
        self.assertNotIn("outside-value", before)

    def test_committed_selectors_are_isolated_from_the_other_controls(self):
        page = self.page()
        for modes in ({"enabled": False}, {"enabled": True, "hard": True},
                      {"enabled": False, "read": True}, {"enabled": True, "hard": True, "read": True}):
            with self.subTest(modes=modes):
                self.post("/chaos", modes)
                self.expect(page.locator("#out-value")).to_have_attribute("data-testid", "result-value" if modes.get("read") else "saved-value")
                for field, selector in self.baseline["fields"].items():
                    missing = field == "save_button" and modes["enabled"] or field == "saved_value" and modes.get("read")
                    self.expect(page.locator(selector)).to_have_count(0 if missing else 1)
                self.expect(page.locator(SAVE)).to_have_count(1 if modes["enabled"] else 0)
                self.assertEqual(page.locator("form").count(), 1)
                for label in ("Record ID", "New value"):
                    self.assertEqual(page.get_by_role("textbox", name=label, exact=True).count(), 1)
                self.assertEqual(page.get_by_role("button", name="Save record", exact=True).count(), 1)

    def test_navigation_pagination_and_numeric_sort(self):
        page = self.page()
        self.expect(page.locator("#inventory-count")).to_have_text("12 records / Page 1 of 2")
        page.locator("#next-page").click()
        self.expect(page.locator("#records-body tr")).to_have_count(4)
        self.expect(page.locator("#next-page")).to_be_disabled()
        page.locator("#previous-page").click()
        self.expect(page.locator("#records-body tr")).to_have_count(8)
        self.expect(page.locator("#previous-page")).to_be_disabled()
        page.get_by_role("button", name="Sort by Price", exact=True).click()
        self.expect(page.locator("#records-body tr").first).to_contain_text("Value: 2.40")
        page.get_by_role("button", name="Sort by Price", exact=True).click()
        self.expect(page.locator("#records-body tr").first).to_contain_text("Value: 42.00")
        page.get_by_label("Filter inventory").fill("no-match-here")
        self.expect(page.locator("#records-body tr")).to_have_count(0)
        self.expect(page.locator("#inventory-empty")).to_be_visible()
        self.expect(page.locator("#inventory-count")).to_have_text("0 records / Page 1 of 1")
        page.get_by_label("Filter inventory").fill("SKU-1053")
        self.expect(page.locator("#records-body tr")).to_have_count(1)
        for label, heading in (("Orders", "Open orders"), ("Suppliers", "Supplier directory"), ("Reports", "Operations reports")):
            page.get_by_role("link", name=label, exact=True).click()
            self.expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
            page.get_by_role("link", name="Inventory", exact=True).click()
            self.expect(page.locator("#sync-status")).to_contain_text("Inventory connected")

    def test_external_save_reveals_filtered_record_and_does_not_keep_changing_pages(self):
        page = self.page()
        page.locator("#next-page").click()
        page.get_by_label("Filter inventory").fill("safety")
        page.get_by_label("Category", exact=True).select_option("Safety")
        page.get_by_role("button", name="Sort by Price", exact=True).click()
        page.locator("#record-id").fill("unfinished-id")
        page.locator("#record-value").fill("unfinished-value")
        payload = self.request("SKU-1042", "3.00")
        self.assertEqual(payload["status"], "success", payload)
        self.expect(page.locator("#records-body")).to_contain_text("Value: 3.00")
        self.expect(page.get_by_label("Filter inventory")).to_have_value("")
        self.expect(page.get_by_label("Category", exact=True)).to_have_value("")
        self.expect(page.locator("#record-id")).to_have_value("unfinished-id")
        self.expect(page.locator("#record-value")).to_have_value("unfinished-value")
        page.locator("#next-page").click()
        self.expect(page.locator("#inventory-count")).to_contain_text("Page 2 of 2")
        with page.expect_response("**/state"):
            pass
        self.expect(page.locator("#inventory-count")).to_contain_text("Page 2 of 2")
        page.get_by_label("Filter inventory").fill("no-match-here")
        page.get_by_label("Category", exact=True).select_option("Tools")
        self.save(page, "custom-item", "custom-value")
        self.expect(page.locator("#records-body")).to_contain_text("Value: custom-value")
        self.assertEqual(self.state()["inventory"]["custom-item"], {"name": "Custom record", "category": "Other", "quantity": 0})

    def test_unchanged_polls_preserve_inventory_and_audit_nodes(self):
        page = self.page()
        self.save(page, "SKU-1042", "19.95")
        self.expect(page.locator("#audit-body tr")).to_have_count(1)
        page.evaluate("""() => { window.inventoryRow = document.querySelector('#records-body tr');
            window.auditRow = document.querySelector('#audit-body tr'); window.saveButton = document.querySelector('#save-btn'); }""")
        for _ in range(2):
            with page.expect_response("**/state"):
                pass
        self.assertTrue(page.evaluate("""() => window.inventoryRow === document.querySelector('#records-body tr') &&
            window.auditRow === document.querySelector('#audit-body tr') && window.saveButton === document.querySelector('#save-btn')"""))
        self.post("/supplier-note", {"supplier": "SUP-017", "note": "Delivery Friday"})
        with page.expect_response("**/state"):
            pass
        self.assertTrue(page.evaluate("() => window.inventoryRow === document.querySelector('#records-body tr')"))

    def test_audit_is_bounded_and_repeated_price_saves_are_safe(self):
        page = self.page()
        for value in ("20.00", "20.00", "21.00", "22.00", "23.00", "24.00", "25.00"):
            self.post("/records", {"record_id": "SKU-1042", "value": value})
        state = self.state()
        self.assertEqual(state["writes"], 7)
        self.assertEqual(len(state["records"]), 12)
        self.assertEqual(len(state["audit"]), 5)
        self.assertEqual((state["audit"][0]["old_value"], state["audit"][0]["new_value"]), ("24.00", "25.00"))
        self.expect(page.locator("#audit-body tr")).to_have_count(5)
        self.post("/reset", {})
        self.expect(page.locator("#audit-body tr")).to_have_count(0)
        self.assertEqual(self.state()["records"], SEEDS)
        self.assertEqual(self.state()["audit"], [])

    def test_note_form_and_reset_are_independent_of_price_writes(self):
        page = self.page()
        frame = page.frame_locator("#supplier-note-frame")
        frame.get_by_label("Supplier reference").fill("SUP-017")
        frame.get_by_label("Supplier note", exact=True).fill("Check next delivery")
        frame.get_by_role("button", name="Attach note").click()
        self.expect(frame.locator("#note-result")).to_contain_text("Note attached")
        state = self.state()
        self.assertEqual((state["records"], state["writes"], state["audit"]), (SEEDS, 0, []))
        self.assertEqual(state["supplier_note"], {"supplier": "SUP-017", "note": "Check next delivery"})
        page.get_by_label("Filter inventory").fill("no-match-here")
        page.get_by_label("Category", exact=True).select_option("Safety")
        self.post("/reset", {})
        self.expect(page.get_by_label("Filter inventory")).to_have_value("")
        self.expect(page.get_by_label("Category", exact=True)).to_have_value("")
        self.expect(frame.get_by_label("Supplier note", exact=True)).to_have_value("")
        self.expect(frame.locator("#note-result")).to_have_text("No supplier note attached.")
        self.assertIsNone(self.state()["supplier_note"])

    def test_real_canary_text_is_unique_after_audit_and_inventory_updates(self):
        page = self.page()
        for read in (False, True):
            self.post("/chaos", {"enabled": False, "read": read})
            self.expect(page.locator("#out-value")).to_have_attribute("data-testid", "result-value" if read else "saved-value")
            self.save(page, "canary-record", "canary-value")
            self.expect(page.locator("#records-body")).to_contain_text("Value: canary-value")
            self.expect(page.locator("#audit-body")).to_contain_text("New price: canary-value")
            for value, expected in (("canary-record", "saved-record"), ("canary-value", "result-value" if read else "saved-value")):
                found = page.evaluate(read_selector_expression((value,)))
                self.assertEqual((found["count"], found["selector"]), (1, f'span[data-testid="{expected}"]'))
                count = page.evaluate("value => [...document.body.querySelectorAll('*')].filter(node => (node.innerText || '').replace(/\\s+/g, ' ').trim() === value).length", value)
                self.assertEqual(count, 1)
        for value in ("Other", "0", "Low"):
            self.save(page, "probe-record", value)
            self.expect(page.locator("#audit-body")).to_contain_text(f"New price: {value}")
            self.assertEqual(page.evaluate(read_selector_expression((value,)))["count"], 1)

    def test_save_works_and_the_site_really_changes(self):
        payload = self.request()
        self.assertEqual((payload["status"], payload["data"]), ("success", {"record_id": "rec-1", "value": "hello"}), payload)
        self.assertEqual(self.state()["records"], {**SEEDS, "rec-1": "hello"})

    def test_chaos_heal_repeats_the_write_idempotently(self):
        self.post("/chaos", {"enabled": True})
        evidence = HealEvidence(action_type="click", history_step=0, action_index=0, node_name="BUTTON",
                                attributes={"data-action": "save"}, reasoning="Mocked unique executed click")
        async def diagnose(settings, workflow, params, failure, **kwargs):
            self.assertEqual(failure.failed_step, "save_button")
            self.assertEqual(self.state()["writes"], 0)
            return Candidate(SAVE, evidence, metrics={"cost_usd": 0.001, "total_tokens": 1})
        self.client.app.state.diagnose = diagnose
        payload = self.request()
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(payload["heal_records"][0]["verification_outcome"], "committed")
        state = self.state()
        # Replay and canary each write once; repeating a set with the same value changes nothing else.
        self.assertEqual(state["records"], {**SEEDS, "rec-1": "hello", "canary-record": "canary-value"})
        self.assertEqual(state["writes"], 2)

    def test_hard_mode_adds_decoys_without_breaking_the_deterministic_heal(self):
        self.post("/chaos", {"enabled": True, "hard": True})
        page = urlopen(f"{self.site}/records", timeout=3).read().decode()
        for decoy in ("Save draft", "Clear form", "Search records"):
            self.assertIn(decoy, page)
        evidence = HealEvidence(action_type="click", history_step=0, action_index=0, node_name="BUTTON",
                                attributes={"data-action": "save"}, reasoning="Mocked unique executed click")

        async def diagnose(settings, workflow, params, failure, **kwargs):
            self.assertEqual(failure.failed_step, "save_button")
            self.assertEqual(self.state()["writes"], 0)
            return Candidate(SAVE, evidence, metrics={"cost_usd": 0.001, "total_tokens": 1})
        self.client.app.state.diagnose = diagnose
        payload = self.request()
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(self.state()["records"]["rec-1"], "hello")
        self.assertTrue(self.state()["hard"])
        self.post("/reset", {})
        self.assertFalse(self.state()["hard"])

    def mocked_read_agent(self, selector, reported):
        evidence = HealEvidence(action_type="read", history_step=3, action_index=0, node_name="SPAN",
                                attributes={"data-testid": "result-value"}, reasoning="Mocked unique visible element")

        async def diagnose(settings, workflow, params, failure, **kwargs):
            self.assertEqual(failure.failed_step, "saved_value")  # only the read is broken
            return Candidate(selector, evidence, metrics={"cost_usd": 0.001, "total_tokens": 1}, reported=reported)
        self.client.app.state.diagnose = diagnose

    def test_read_chaos_breaks_only_the_read_and_a_correct_read_heal_commits(self):
        self.post("/chaos", {"enabled": False, "read": True})
        self.mocked_read_agent('span[data-testid="result-value"]', {"value": "hello"})
        payload = self.request()
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(payload["data"], {"record_id": "rec-1", "value": "hello"})
        record = payload["heal_records"][0]
        self.assertEqual((record["field"], record["verification_outcome"], record["evidence"]["action_type"]),
                         ("saved_value", "committed", "read"))
        self.assertEqual(json.loads(self.path.read_text())["fields"]["saved_value"], 'span[data-testid="result-value"]')
        self.assertEqual(self.request("after", "x")["status"], "success")

    def test_a_read_heal_that_reads_a_different_element_than_reported_is_rolled_back(self):
        self.post("/chaos", {"enabled": False, "read": True})
        # The record span shows "rec-1", but the agent claimed it saw "hello".
        self.mocked_read_agent('span[data-testid="saved-record"]', {"value": "hello"})
        payload = self.request()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["code"], "read_mismatch")
        self.assertEqual(payload["heal_records"][0]["verification_outcome"], "rolled_back")
        self.assertEqual(json.loads(self.path.read_text())["fields"]["saved_value"], "[data-testid='saved-value']")

    def test_the_canary_alone_rejects_a_wrong_read_element(self):
        self.post("/chaos", {"enabled": False, "read": True})
        # No reported values to cross-check, so only the canary (value must be "canary-value") can catch this.
        self.mocked_read_agent('span[data-testid="saved-record"]', None)
        payload = self.request("same", "same-text")
        self.assertEqual((payload["status"], payload["error"]["code"]), ("failed", "canary_failed"))
        self.assertEqual(payload["heal_records"][0]["verification_outcome"], "rolled_back")

    @unittest.skipUnless(os.getenv("MENDER_LIVE_TEST") == "1", "Set MENDER_LIVE_TEST=1 for paid Gemini calls")
    def test_gemini_heals_the_save_button_on_the_sandbox(self):
        from dotenv import load_dotenv
        load_dotenv(ROOT / "services/backend/.env", override=False)
        self.client.app.state.diagnose = None
        self.post("/chaos", {"enabled": True})
        started = time.perf_counter()
        payload = self.request("live-rec", "live-value")
        state = self.state()
        print(f"sandbox Gemini heal: {time.perf_counter() - started:.1f} s; cost {payload.get('agent_cost_usd')}; "
              f"agent_ms {payload.get('agent_duration_ms')}; writes {state['writes']}; "
              f"selector {json.loads(self.path.read_text())['fields']['save_button']}")
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(state["records"].get("live-rec"), "live-value")
        self.assertEqual(state["records"].get("canary-record"), "canary-value")
        self.assertEqual(self.request("after", "x")["status"], "success")


    @unittest.skipUnless(os.getenv("MENDER_LIVE_TEST") == "1", "Set MENDER_LIVE_TEST=1 for paid Gemini calls")
    def test_gemini_heals_a_broken_read_selector_on_the_sandbox(self):
        from dotenv import load_dotenv
        load_dotenv(ROOT / "services/backend/.env", override=False)
        self.client.app.state.diagnose = None
        self.post("/chaos", {"enabled": False, "read": True})
        started = time.perf_counter()
        payload = self.request("live-read", "live-read-value")
        print(f"sandbox Gemini READ heal: {time.perf_counter() - started:.1f} s; cost {payload.get('agent_cost_usd')}; "
              f"records {[(r['field'], r['verification_outcome'], r['evidence']['action_type']) for r in payload.get('heal_records', [])]}; "
              f"selector {json.loads(self.path.read_text())['fields']['saved_value']}")
        self.assertEqual(payload["status"], "healed", payload)
        self.assertEqual(payload["data"], {"record_id": "live-read", "value": "live-read-value"})
        self.assertEqual([(r["field"], r["verification_outcome"], r["evidence"]["action_type"]) for r in payload["heal_records"]],
                         [("saved_value", "committed", "read")])
        self.assertEqual(self.request("after", "x")["status"], "success")


if __name__ == "__main__":
    unittest.main()
