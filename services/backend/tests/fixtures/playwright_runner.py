"""Opt-in local integration fixture implementing Person 1's CLI for tests."""

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
    args = parser.parse_args()
    params = json.loads(args.params)
    selectors = json.loads(Path(f"contracts/selectors/{args.workflow}.json").read_text())
    directory = Path("runs") / args.run_id
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, executable_path=os.environ.get("MENDER_BROWSER_EXECUTABLE")
        )
        page = await browser.new_page()
        field = "input_reference"
        try:
            await page.goto(selectors["target_url"])
            await page.locator(selectors["fields"][field]).fill(params["record_id"], timeout=2000)
            field = "submit_button"
            await page.locator(selectors["fields"][field]).click(timeout=2000)
            print(await page.locator("[data-result]").inner_text())
            return 0
        except Exception:
            directory.mkdir(parents=True)
            await page.screenshot(path=str(directory / "failure.png"))
            failure = {
                "workflow_id": args.workflow, "timestamp": time.time() * 1000,
                "failed_step": field, "expected_selector": selectors["fields"][field],
                "page_url": page.url, "dom_snippet": (await page.content())[:8000],
                "screenshot_path": str(directory / "failure.png"),
                "error_message": "Local fixture could not resolve its selector",
            }
            (directory / "failure_payload.json").write_text(json.dumps(failure))
            return 1
        finally:
            await browser.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
