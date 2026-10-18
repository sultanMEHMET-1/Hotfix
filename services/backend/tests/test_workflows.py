"""Several workflows on one backend: routing, lock and cooldown isolation, per-workflow reset."""

import asyncio
from dataclasses import replace
import json
import subprocess

import httpx

from services.backend.config import BackendError
from services.backend.main import create_app
from services.backend.tests.support import make_root
from services.backend.tests.test_m2 import M2Harness


class MultiWorkflowTests(M2Harness):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.other_baseline = {**self.baseline, "workflow_id": "other-lookup"}
        self.other_path = make_root(self.root, "other-lookup", self.definition, self.other_baseline)
        self.git(["init", "-q"])
        self.git(["add", "contracts/selectors"])
        self.git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline"])
        self.counts = {"sample-lookup": 0, "other-lookup": 0}
        app = create_app(self.settings)
        self.lifespan2 = app.router.lifespan_context(app)
        await self.lifespan2.__aenter__()
        self.addAsyncCleanup(self.lifespan2.__aexit__, None, None, None)
        self.addAsyncCleanup(self.close_client)
        self.multi = app
        self.multi_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://backend.test")

    async def close_client(self):
        await self.multi_client.aclose()

    def git(self, args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def read(self, path):
        return json.loads(path.read_text())

    async def run_workflow(self, workflow, record_id="r"):
        return (await self.multi_client.post("/api/v1/run-workflow",
                json={"workflow": workflow, "params": {"record_id": record_id}})).json()

    def count_calls(self, app):
        """Count agent calls per workflow by wrapping the failing diagnose with the failed workflow's id."""
        async def diagnose(settings, workflow, params, failed, **kwargs):
            self.counts[failed.workflow_id] += 1
            raise BackendError("ambiguous_element", "Not unique")
        app.state.diagnose = diagnose

    async def test_workflows_endpoint_lists_both_with_the_default_first(self):
        listing = (await self.multi_client.get("/api/v1/workflows")).json()
        self.assertEqual([w["id"] for w in listing], ["other-lookup", "sample-lookup"])  # no permit workflow here: alphabetical
        self.assertEqual([w["default"] for w in listing], [True, False])
        self.assertEqual(listing[0]["example_params"], self.definition["canary"]["params"])
        self.assertIn("record_id", listing[0]["params_schema"]["properties"])

    async def test_each_request_uses_its_own_workflow_map(self):
        self.path.write_text(json.dumps({**self.baseline, "fields": {"submit_button": "#reference", "input_reference": "#reference"}}))
        self.other_path.write_text(json.dumps({**self.other_baseline,
                                               "fields": {"submit_button": 'button[data-action="lookup"]', "input_reference": "#reference"}}))
        self.assertEqual((await self.run_workflow("other-lookup"))["status"], "success")
        self.assertEqual((await self.run_workflow("sample-lookup"))["status"], "failed")

    async def test_one_workflows_lock_never_blocks_the_other(self):
        self.other_path.write_text(json.dumps({**self.other_baseline,
                                               "fields": {"submit_button": 'button[data-action="lookup"]', "input_reference": "#reference"}}))
        async with self.multi.state.stores["sample-lookup"].lock(exclusive=True):
            started = asyncio.get_running_loop().time()
            other = await asyncio.wait_for(self.run_workflow("other-lookup"), 2)
            self.assertEqual(other["status"], "success")
            self.assertLess(asyncio.get_running_loop().time() - started, 1)
            blocked = await self.run_workflow("sample-lookup")
            self.assertEqual(blocked["error"]["code"], "lock_timeout")

    async def test_a_failure_cooldown_is_per_workflow(self):
        self.count_calls(self.multi)
        await self.run_workflow("sample-lookup")
        await self.run_workflow("sample-lookup")           # served from the cooldown
        await self.run_workflow("other-lookup")            # same failure shape, different workflow: fresh recovery
        self.assertEqual(self.counts, {"sample-lookup": 1, "other-lookup": 1})
        self.assertEqual(set(self.multi.state.recovery.cooldown), {"sample-lookup", "other-lookup"})

    async def test_reset_one_workflow_leaves_the_other_alone(self):
        self.count_calls(self.multi)
        for name, path, base in (("sample-lookup", self.path, self.baseline), ("other-lookup", self.other_path, self.other_baseline)):
            path.write_text(json.dumps({**base, "version": 5, "fields": {**base["fields"], "submit_button": "#drifted"}}))
            await self.run_workflow(name)
        self.assertEqual(set(self.multi.state.recovery.cooldown), {"sample-lookup", "other-lookup"})
        reply = (await self.multi_client.post("/api/v1/admin/reset", json={"workflow": "sample-lookup"})).json()
        self.assertEqual(reply["versions"], {"sample-lookup": 6})
        self.assertEqual(reply["version"], 6)
        self.assertEqual(self.read(self.path)["fields"], self.baseline["fields"])
        self.assertEqual(self.read(self.other_path)["fields"]["submit_button"], "#drifted")
        self.assertEqual(set(self.multi.state.recovery.cooldown), {"other-lookup"})

    async def test_reset_all_and_unknown_workflow(self):
        for path, base in ((self.path, self.baseline), (self.other_path, self.other_baseline)):
            path.write_text(json.dumps({**base, "version": 3, "fields": {**base["fields"], "submit_button": "#drifted"}}))
        reply = (await self.multi_client.post("/api/v1/admin/reset")).json()  # no body at all
        self.assertEqual(reply["versions"], {"other-lookup": 4, "sample-lookup": 4})
        self.assertEqual(self.read(self.path)["fields"], self.baseline["fields"])
        self.assertEqual(self.read(self.other_path)["fields"], self.other_baseline["fields"])
        self.assertEqual((await self.multi_client.post("/api/v1/admin/reset", json={"workflow": "nope"})).status_code, 404)

    async def test_reset_rejects_a_malformed_body_without_touching_any_map(self):
        for path, base in ((self.path, self.baseline), (self.other_path, self.other_baseline)):
            path.write_text(json.dumps({**base, "version": 3, "fields": {**base["fields"], "submit_button": "#drifted"}}))
        for body in (b'{"workflow": "sample-lookup"', b"[]", b'{"workflow": []}', b'{"workflow": 5}'):
            with self.subTest(body=body):
                reply = await self.multi_client.post("/api/v1/admin/reset", content=body, headers={"content-type": "application/json"})
                self.assertEqual(reply.status_code, 422)
        self.assertEqual(self.read(self.path)["fields"]["submit_button"], "#drifted")
        self.assertEqual(self.read(self.other_path)["fields"]["submit_button"], "#drifted")

    async def test_reset_all_changes_nothing_when_one_committed_map_is_missing(self):
        for path, base in ((self.path, self.baseline), (self.other_path, self.other_baseline)):
            path.write_text(json.dumps({**base, "version": 3, "fields": {**base["fields"], "submit_button": "#drifted"}}))
        self.git(["rm", "-q", "--cached", "contracts/selectors/other-lookup.json"])
        self.git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "drop"])
        reply = await self.multi_client.post("/api/v1/admin/reset")
        self.assertEqual(reply.status_code, 500)
        self.assertEqual(self.read(self.path)["fields"]["submit_button"], "#drifted")  # not half reset
        self.assertEqual(self.read(self.other_path)["version"], 3)

    async def test_reset_works_when_startup_stopped_before_the_default_workflow_was_chosen(self):
        for path, base in ((self.path, self.baseline), (self.other_path, self.other_baseline)):
            path.write_text(json.dumps({**base, "version": 3, "fields": {**base["fields"], "submit_button": "#drifted"}}))
        self.multi.state.default_workflow = None
        reply = (await self.multi_client.post("/api/v1/admin/reset")).json()
        self.assertEqual(reply["versions"], {"other-lookup": 4, "sample-lookup": 4})
        self.assertIsNotNone(reply["version"])

    async def test_reset_refuses_only_a_workflow_that_is_recovering(self):
        gate = asyncio.Event()

        async def slow(settings, workflow, params, failed, **kwargs):
            await gate.wait()
            raise BackendError("ambiguous_element", "Not unique")
        self.multi.state.diagnose = slow
        running = asyncio.create_task(self.run_workflow("sample-lookup"))
        try:
            await asyncio.sleep(0.2)
            self.assertEqual((await self.multi_client.post("/api/v1/admin/reset", json={"workflow": "sample-lookup"})).status_code, 409)
            self.assertEqual((await self.multi_client.post("/api/v1/admin/reset", json={})).status_code, 409)
            self.assertEqual((await self.multi_client.post("/api/v1/admin/reset", json={"workflow": "other-lookup"})).status_code, 200)
        finally:
            gate.set()
            await running

    async def test_a_map_that_is_inconsistent_with_its_definition_blocks_startup_clearly(self):
        for label, change in (("another workflow's id", {"workflow_id": "sample-lookup"}),
                              ("a missing field", {"fields": {"submit_button": "#x"}})):
            with self.subTest(case=label):
                self.other_path.write_text(json.dumps({**self.other_baseline, **change}))
                app = create_app(replace(self.settings))
                async with app.router.lifespan_context(app):
                    self.assertIsNotNone(app.state.configuration_error)
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://backend.test") as client:
                        self.assertEqual((await client.get("/api/v1/workflows")).status_code, 503)
