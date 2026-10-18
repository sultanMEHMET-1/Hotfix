"""Test-only wrapper that points the real runner at a temp selector map and portal port.

The runner now speaks the agreed CLI itself. In production the backend root is the repository,
so the runner finds its selector map on its own; tests use a temp root and a free port,
so this wrapper only adds --selectors and --target-url and forwards everything else.
"""

import os
from pathlib import Path
import subprocess
import sys


workflow = sys.argv[sys.argv.index("--workflow") + 1]
command = [os.environ["REAL_RUNNER_PYTHON"], os.environ["REAL_RUNNER_SCRIPT"],
           "--selectors", str(Path(f"contracts/selectors/{workflow}.json").resolve()),
           "--target-url", os.environ["REAL_PORTAL_URL"], *sys.argv[1:]]
sys.exit(subprocess.run(command, env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": os.environ["REAL_PLAYWRIGHT_BROWSERS"]}).returncode)
