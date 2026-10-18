"""Real DOM selector checks, enabled explicitly; no Gemini calls."""

import os
from pathlib import Path
import unittest

from services.backend.healer import read_selector_expression, selector_expression


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

    async def probe(self, *texts):
        return await self.page.evaluate(read_selector_expression(texts))

    async def test_read_probe_finds_the_one_element_showing_the_text(self):
        await self.page.set_content('<p>intro</p><span data-testid="status">Approved</span>')
        found = await self.probe("Approved")
        self.assertEqual((found["count"], found["selector"], found["tag"]), (1, 'span[data-testid="status"]', "SPAN"))
        self.assertEqual(found["attributes"], {"data-testid": "status"})

    async def test_read_probe_gives_up_when_it_runs_out_of_time(self):
        await self.page.set_content('<span data-testid="status">Approved</span>')
        self.assertEqual((await self.page.evaluate(read_selector_expression(["Approved"], budget_ms=-1)))["count"], -1)
        self.assertEqual((await self.probe("Approved"))["count"], 1)

    async def test_page_text_that_looks_like_a_placeholder_is_not_rewritten(self):
        await self.page.set_content('<h1>BUDGET FORGIVING TEXTS</h1>')
        found = await self.page.evaluate(read_selector_expression(["BUDGET FORGIVING TEXTS"], forgiving=True))
        self.assertEqual((found["count"], found["tag"]), (1, "H1"))

    async def test_read_probe_ignores_hidden_duplicates(self):
        await self.page.set_content('<span id="sticky" style="display:none">Approved</span><span data-testid="status">Approved</span>')
        found = await self.probe("Approved")
        self.assertEqual((found["count"], found["selector"]), (1, 'span[data-testid="status"]'))

    async def test_forgiving_probe_prefers_the_heading_then_the_closest_text_and_leaves_repairs_strict(self):
        await self.page.set_content('<h1><span id="title">Marie Curie</span></h1><a href="#">Marie Curie</a><p>Marie Curie</p>')
        strict = await self.probe("Marie Curie")
        self.assertEqual(strict["count"], 3)  # a repair still refuses the ambiguity
        forgiving = await self.page.evaluate(read_selector_expression(["Marie Curie"], forgiving=True))
        self.assertEqual((forgiving["count"], forgiving["selector"]), (1, 'span[id="title"]'))
        await self.page.set_content('<a id="a">Download Python 3.15.0</a><a id="b">Python 3.15.0</a>')
        shortest = await self.page.evaluate(read_selector_expression(["3.15.0"], forgiving=True))
        self.assertEqual((shortest["selector"], shortest["text"]), ('a[id="b"]', "Python 3.15.0"))
        self.assertEqual((await self.probe("3.15.0"))["count"], 0)

    async def test_read_probe_ignores_wrappers_that_only_contain_the_match(self):
        await self.page.set_content('<div id="outer"><div id="inner"><span data-testid="status">Approved</span></div></div>')
        self.assertEqual((await self.probe("Approved"))["selector"], 'span[data-testid="status"]')

    async def test_read_probe_refuses_duplicates_and_missing_text(self):
        await self.page.set_content('<span>Approved</span><b>Approved</b>')
        self.assertEqual((await self.probe("Approved"))["count"], 2)
        self.assertEqual((await self.probe("Rejected"))["count"], 0)

    async def test_read_probe_skips_form_controls_that_echo_a_value(self):
        await self.page.set_content('<input value="Approved"><textarea>Approved</textarea><select><option>Approved</option></select>'
                                    '<span data-testid="status">Approved</span>')
        self.assertEqual((await self.probe("Approved"))["selector"], 'span[data-testid="status"]')

    async def test_read_probe_is_case_sensitive_and_collapses_whitespace(self):
        await self.page.set_content('<h1>APPROVED</h1><span data-testid="status">  Approved \n </span>')
        self.assertEqual((await self.probe("Approved"))["selector"], 'span[data-testid="status"]')

    async def test_read_probe_falls_back_to_structural_css_without_attributes(self):
        await self.page.set_content('<p>intro</p><p>Approved</p>')
        found = await self.probe("Approved")
        self.assertEqual(found["selector"], "p:nth-of-type(2)")
        self.assertEqual(await self.page.locator(found["selector"]).inner_text(), "Approved")
