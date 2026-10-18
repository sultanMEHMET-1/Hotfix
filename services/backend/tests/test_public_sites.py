"""Live checks of the two built-in public workflows. Free (no model), but they need the internet and the real sites,
so they only run with MENDER_PUBLIC_TEST=1 and the project venv (services/runner/setup_venv.sh)."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
VENV_PYTHON = ROOT / ".venv/bin/python"


def run_workflow(workflow, params):
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / ".venv/playwright-browsers")}
        result = subprocess.run(
            [str(VENV_PYTHON), str(ROOT / "services/runner/execute.py"), "--workflow", workflow, "--params", json.dumps(params),
             "--run-id", "public-check", "--contracts", str(ROOT / "contracts")],
            cwd=directory, capture_output=True, text=True, timeout=60, env=env)
        return result.returncode, result.stdout, result.stderr


@unittest.skipUnless(os.getenv("MENDER_PUBLIC_TEST") == "1" and VENV_PYTHON.is_file(),
                     "Set MENDER_PUBLIC_TEST=1 (and run services/runner/setup_venv.sh) for live public-site checks")
class PublicSiteTests(unittest.TestCase):
    def test_wikipedia_opens_the_searched_article(self):
        code, out, err = run_workflow("wikipedia-article", {"title": "Ada Lovelace"})
        self.assertEqual(code, 0, err[-400:])
        self.assertEqual(json.loads(out), {"heading": "Ada Lovelace"})

    def test_python_org_reports_a_release_number(self):
        code, out, err = run_workflow("python-latest-release", {})
        self.assertEqual(code, 0, err[-400:])
        self.assertRegex(json.loads(out)["release"], re.compile(r"^Python \d+\.\d+\.\d+"))


if __name__ == "__main__":
    unittest.main()
