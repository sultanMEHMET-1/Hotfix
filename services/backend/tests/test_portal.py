import importlib.util
import random
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2] / "portal" / "server.py"


def portal():
    spec = importlib.util.spec_from_file_location("portal_server", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortalBreakTests(unittest.TestCase):
    def test_every_click_breaks_something_new_within_the_selector_cap(self):
        module = portal()
        state, rng = module.PortalState(), random.Random(3)
        seen = set()
        for _ in range(200):
            before = state.snapshot()
            state.next_break(rng)
            after = state.snapshot()
            self.assertNotEqual(before, after)
            self.assertLessEqual(len(after["variants"]), module.MAX_SELECTOR_BREAKS)
            seen.update((key, n) for key, n in after["variants"].items())
        self.assertGreater(len(seen), 3)

    def test_the_original_switch_still_means_the_button_dialog(self):
        module = portal()
        state = module.PortalState()
        state.set_chaos_enabled(True)
        self.assertEqual(state.snapshot()["variants"], {"button": 0})
        self.assertTrue(state.is_chaos_enabled())
        state.set_chaos_enabled(False)
        self.assertEqual(state.snapshot(), {"enabled": False, "variants": {}, "decoys": False, "last": None})

    def test_an_unknown_change_is_refused_and_changes_nothing(self):
        module = portal()
        state = module.PortalState()
        for key, variant in (("nope", 0), ("button", 9), ("button", -1)):
            with self.assertRaises(ValueError):
                state.apply(key, variant)
        self.assertFalse(state.is_chaos_enabled())


if __name__ == "__main__":
    unittest.main()
