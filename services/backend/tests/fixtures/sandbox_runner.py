"""Opt-in fixture runner for the record-update workflow, implementing the agreed CLI."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

from playwright.async_api import async_playwright


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--params", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sentry-trace")
    parser.add_argument("--baggage")
    args = parser.parse_args()
    params = json.loads(args.params)
    selectors = json.loads(Path("contracts/selectors.json").read_text())
    fields = selectors["fields"]
    directory = Path("runs") / args.run_id
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, executable_path=os.environ.get("MENDER_BROWSER_EXECUTABLE") or None)
        page = await browser.new_page()
        step = "input_record_id"
        try:
            await page.goto(selectors["target_url"])
            await page.locator(fields[step]).fill(params["record_id"], timeout=2000)
            step = "input_value"
            await page.locator(fields[step]).fill(params["value"], timeout=2000)
            step = "save_button"
            await page.locator(fields[step]).click(timeout=2000)
            step = "saved_value"
            badge = page.locator(fields[step])
            await badge.wait_for(state="visible", timeout=2000)
            print(json.dumps({"record_id": await badge.get_attribute("data-record"),
                              "value": await badge.get_attribute("data-value")}))
            return 0
        except Exception as error:
            directory.mkdir(parents=True)
            await page.screenshot(path=str(directory / "failure.png"))
            html = await page.locator("form").evaluate("element => element.outerHTML")
            (directory / "failure_payload.json").write_text(json.dumps({
                "workflow_id": args.workflow, "timestamp": time.time() * 1000, "failed_step": step,
                "expected_selector": fields[step], "page_url": page.url, "dom_snippet": " ".join(html.split())[:1500],
                "screenshot_path": str(directory / "failure.png"),
                "error_message": f"{type(error).__name__}: selector {fields[step]}"}))
            return 1
        finally:
            await browser.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
