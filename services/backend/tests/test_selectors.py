"""Real DOM selector checks, enabled explicitly; no Gemini calls."""

import os
from pathlib import Path
import unittest

from services.backend.healer import selector_expression


@unittest.skipUnless(os.getenv("MENDER_BROWSER_TEST") == "1", "Set MENDER_BROWSER_TEST=1 for real DOM checks")
class SelectorBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        executable = os.getenv("MENDER_BROWSER_EXECUTABLE")
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if not executable and Path(chrome).is_file():
            executable = chrome
        self.browser = await self.playwright.chromium.launch(headless=True, executable_path=executable)
        self.page = await self.browser.new_page()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def selector(self, xpath, attributes):
        return await self.page.evaluate(selector_expression({"node_name": "BUTTON", "x_path": xpath, "attributes": attributes}))

    async def test_class_only_chaos_prefers_stable_attributes(self):
        await self.page.set_content('<button>Other</button><button class="lookup-old" data-action="lookup">Look up record</button>')
        await self.page.locator('[data-action="lookup"]').evaluate("node => node.className = 'lookup-chaos'")
        self.assertEqual(await self.page.locator(".lookup-old").count(), 0)
        selector = await self.selector("/html/body/button[2]", {"class": "lookup-chaos", "data-action": "lookup"})
        self.assertEqual(selector, 'button[data-action="lookup"]')
        self.assertEqual(await self.page.locator(selector).inner_text(), "Look up record")

    async def test_class_only_target_uses_unique_structural_css(self):
        await self.page.set_content('<button>Other</button><button class="lookup-old">Look up record</button>')
        await self.page.locator(".lookup-old").evaluate("node => node.className = 'lookup-chaos'")
        selector = await self.selector("/html/body/button[2]", {"class": "lookup-chaos"})
        self.assertNotIn("class", selector)
        self.assertIn(":nth-of-type(2)", selector)
        self.assertEqual(await self.page.locator(selector).count(), 1)
        self.assertEqual(await self.page.locator(selector).inner_text(), "Look up record")

    async def test_missing_live_target_has_no_candidate(self):
        await self.page.set_content('<button>Other</button>')
        self.assertIsNone(await self.selector("/html/body/button[2]", {}))

    async def test_attribute_quotes_are_escaped(self):
        await self.page.set_content('<button>Other</button><button>Target</button>')
        value = 'lookup"quoted\\value'
        await self.page.locator("button").nth(1).evaluate("(node, value) => node.setAttribute('data-testid', value)", value)
        selector = await self.selector("/html/body/button[2]", {"data-testid": value})
        self.assertIn("data-testid", selector)
        self.assertEqual(await self.page.locator(selector).inner_text(), "Target")

    async def test_international_attribute_remains_a_stable_candidate(self):
        await self.page.set_content('<button>Other</button><button data-testid="référence">Target</button>')
        selector = await self.selector("/html/body/button[2]", {"data-testid": "référence"})
        self.assertEqual(selector, 'button[data-testid="référence"]')
