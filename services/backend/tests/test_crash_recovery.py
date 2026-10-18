"""Crash recovery (interrupted recoveries are restored at startup) and failure-artifact pruning."""

import json
import os
import time
from unittest.mock import patch

import httpx

from services.backend.config import BackendError, prune_runs
from services.backend.main import create_app
from services.backend.store import SelectorStore
from services.backend.tests.test_m1 import CORRECT
from services.backend.tests.test_m2 import M2Harness


class CrashRecoveryTests(M2Harness):
    def store(self):
        return SelectorStore(self.settings, "sample-lookup")

    @property
    def marker(self):
        return self.settings.backend / "state/inflight-sample-lookup.json"

    def simulate_crash_after_a_provisional_patch(self):
        """What a killed process leaves behind: a backup, an in-flight marker, and a patched map."""
        store = self.store()
        backup = store.backup("crashed-run", self.baseline)
        store.mark_inflight(backup, self.baseline["version"])
        self.path.write_text(json.dumps({**self.baseline, "version": 2,
                                         "fields": {**self.baseline["fields"], "submit_button": CORRECT}}))

    async def start(self):
        app = create_app(self.settings)
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        self.addAsyncCleanup(lifespan.__aexit__, None, None, None)
        return app

    async def test_an_interrupted_recovery_is_restored_at_startup(self):
        self.simulate_crash_after_a_provisional_patch()
        app = await self.start()
        self.assertIsNone(app.state.configuration_error)
        restored = json.loads(self.path.read_text())
        self.assertEqual(restored["fields"], self.baseline["fields"])
        self.assertEqual(restored["version"], 3)  # a new version above the provisional one, never reused
        self.assertFalse(self.marker.exists())

    async def test_an_old_backup_without_a_marker_is_never_restored(self):
        self.store().backup("an-old-run", {**self.baseline, "fields": {**self.baseline["fields"], "submit_button": "#stale"}})
        self.path.write_text(json.dumps({**self.baseline, "version": 4,
                                         "fields": {**self.baseline["fields"], "submit_button": CORRECT}}))  # a committed heal
        await self.start()
        self.assertEqual(json.loads(self.path.read_text())["fields"]["submit_button"], CORRECT)
        self.assertEqual(json.loads(self.path.read_text())["version"], 4)

    async def test_a_marker_whose_backup_is_gone_blocks_instead_of_guessing(self):
        self.store().mark_inflight(self.settings.backend / "state/baseline-missing.json", 1)
        app = await self.start()
        self.assertIsNotNone(app.state.configuration_error)

    async def test_the_marker_exists_only_while_a_recovery_is_in_flight(self):
        seen = []

        async def diagnose(settings, workflow, params, failed, **kwargs):
            seen.append(self.marker.exists())
            return await self.diagnose(settings, workflow, params, failed, **kwargs)
        self.app.state.diagnose = diagnose
        self.assertEqual((await self.request()).json()["status"], "healed")
        self.assertEqual(seen, [True, True])
        self.assertFalse(self.marker.exists())  # cleared after a commit

    async def test_the_marker_is_cleared_after_every_outcome_that_restored_or_installed_nothing(self):
        async def ambiguous(*args, **kwargs):
            raise BackendError("ambiguous_element", "Not unique")
        self.app.state.diagnose = ambiguous
        await self.request()
        self.assertFalse(self.marker.exists())  # nothing installed
        self.app.state.recovery.cooldown.clear()

        async def poisoned(settings, workflow, params, failed, **kwargs):
            candidate = await self.diagnose(settings, workflow, params, failed, **kwargs)
            candidate.selector = "#still-broken"
            return candidate
        self.app.state.diagnose = poisoned
        await self.request()
        self.assertFalse(self.marker.exists())  # installed, then rolled back

    async def test_a_failed_rollback_keeps_the_marker_so_startup_can_retry(self):
        async def poisoned(settings, workflow, params, failed, **kwargs):
            candidate = await self.diagnose(settings, workflow, params, failed, **kwargs)
            candidate.selector = "#still-broken"
            return candidate
        self.app.state.diagnose = poisoned
        with patch.object(self.app.state.stores["sample-lookup"], "restore", side_effect=OSError("disk")):
            payload = (await self.request()).json()
        self.assertEqual(payload["error"]["code"], "rollback_failed")
        self.assertTrue(self.marker.exists())
        app = await self.start()  # a fresh process: the provisional patch is undone
        self.assertEqual(json.loads(self.path.read_text())["fields"], self.baseline["fields"])
        self.assertFalse(self.marker.exists())
        self.assertIsNone(app.state.configuration_error)


class PruneRunsTests(M2Harness):
    def test_keeps_the_newest_folders_and_leaves_files_alone(self):
        runs = self.root / "runs"
        runs.mkdir()
        now = time.time()
        for age in range(8):
            folder = runs / f"run-{age}"
            folder.mkdir()
            os.utime(folder, (now - age * 100, now - age * 100))
        (runs / "notes.txt").write_text("keep me")
        self.assertEqual(prune_runs(runs, keep=5), 3)
        self.assertEqual(sorted(p.name for p in runs.iterdir() if p.is_dir()), [f"run-{i}" for i in range(5)])
        self.assertTrue((runs / "notes.txt").exists())
        self.assertEqual(prune_runs(runs, keep=5), 0)
        self.assertEqual(prune_runs(self.root / "no-such-folder"), 0)

    async def test_startup_prunes_old_runs_without_blocking(self):
        runs = self.root / "runs"
        runs.mkdir()
        for index in range(60):
            (runs / f"run-{index:02d}").mkdir()
            os.utime(runs / f"run-{index:02d}", (1000 + index, 1000 + index))
        app = create_app(self.settings)
        async with app.router.lifespan_context(app):
            self.assertIsNone(app.state.configuration_error)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://backend.test") as client:
                self.assertEqual((await client.get("/api/v1/workflows")).status_code, 200)
        left = sorted(p.name for p in runs.iterdir())
        self.assertEqual(len(left), 50)
        self.assertIn("run-59", left)
        self.assertNotIn("run-00", left)
