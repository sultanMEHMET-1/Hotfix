"""Browser rehearsal of the real demo through the dashboard. Paid: one Gemini heal per loop.

Run from the repository root with the project venv (it has Playwright), with the portal on
:3000, the backend on :8000, and the dashboard running with mocks off on :5173:

  PLAYWRIGHT_BROWSERS_PATH=.venv/playwright-browsers .venv/bin/python services/backend/rehearse_ui.py 3

Each loop: click "Reset selectors", Chaos Mode off, run (expect the fast path), Chaos Mode on,
run (expect a committed heal), run again (expect the fast path). Exits 1 if any loop fails.
"""

import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

DASHBOARD = "http://127.0.0.1:5173"
PORTAL = "http://127.0.0.1:3000"


def chaos(enabled):
    request = Request(f"{PORTAL}/chaos", json.dumps({"enabled": enabled}).encode(),
                      {"content-type": "application/json"}, method="POST")
    urlopen(request, timeout=3).read()


def run_once(page, expect):
    """Click Trigger, wait for the run to finish, then require every expected text on the page."""
    started = time.perf_counter()
    page.get_by_role("button", name="Trigger workflow").click()
    page.wait_for_selector("button:has-text('Trigger workflow')", timeout=300_000)
    page.wait_for_timeout(400)
    elapsed = time.perf_counter() - started
    body = page.locator("body").inner_text()
    missing = [text for text in expect if text not in body]
    return elapsed, missing


def main():
    loops = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    shots = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    failures = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.goto(DASHBOARD)
        page.wait_for_selector("text=Trigger workflow")
        if page.get_by_role("button", name="Mocks off").count() == 0:
            sys.exit("The dashboard is in mock mode; start it with VITE_USE_MOCKS=false")
        for loop in range(1, loops + 1):
            chaos(False)
            page.get_by_role("button", name="Reset selectors").click()
            page.get_by_role("status").filter(has_text="Selectors reset").wait_for(timeout=15_000)
            fast, miss_fast = run_once(page, ["Deterministic Playwright"])
            chaos(True)
            heal, miss_heal = run_once(page, ["Healed, selector patched", "Browser Use Agent Engaged", "Committed"])
            if shots:
                shots.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shots / f"loop-{loop}-healed.png"), full_page=True)
            after, miss_after = run_once(page, ["Deterministic Playwright"])
            problems = [f"fast run missing {miss_fast}" if miss_fast else "",
                        f"heal run missing {miss_heal}" if miss_heal else "",
                        f"after-heal run missing {miss_after}" if miss_after else ""]
            problems = [p for p in problems if p]
            failures += bool(problems)
            print(f"loop {loop}: fast {fast:.1f}s | heal {heal:.1f}s | after {after:.1f}s | "
                  f"{'PASS' if not problems else 'FAIL ' + '; '.join(problems)}", flush=True)
        browser.close()
    if console_errors:
        failures += 1
        print("browser console errors:", console_errors[:3])
    print(f"RESULT {loops - min(failures, loops)}/{loops} PASS")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
