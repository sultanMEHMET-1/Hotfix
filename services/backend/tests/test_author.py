"""Creating workflows from a sentence: the guards, the compiler, and keeping, loading and deleting what is created."""

import json
import subprocess
from unittest.mock import AsyncMock, patch

import httpx

from services.backend import author, custom
from services.backend.config import BackendError
from services.backend.main import create_app
from services.backend.tests.test_m2 import M2Harness


def plan(**overrides):
    values = {"read_only": True, "goal": "Search for a topic and read the heading.",
              "params": [author.ParamSpec(name="topic", example="Marie Curie", alternate="Grace Hopper")],
              "outputs": [author.OutputSpec(name="heading", description="the heading")]}
    return author.Plan(**{**values, **overrides})


def element(node="INPUT", name="Search", backend_id=1, **extra):
    return {"node_name": node, "ax_name": name, "backend_node_id": backend_id, "x_path": f"html/body/{backend_id}",
            "frame_id": None, "attributes": {}, **extra}


def history(*steps):
    """steps: (action dict, element) pairs, each recorded as one successful history entry."""
    return {"history": [{"model_output": {"action": [action]}, "result": [{"is_done": False}],
                         "state": {"interacted_element": [el]}} for action, el in steps]}


class RequestAndPlanGuards(M2Harness):
    def test_the_request_is_checked_before_any_model_call(self):
        for site, text in (("amazon", "read the heading"), ("wikipedia", "hi"), ("wikipedia", "x" * 301)):
            with self.subTest(text=text[:10]), self.assertRaises(BackendError):
                author.validate_request(site, text)
        for text in ("Edit the Alan Turing article", "log in to python.org", "Change my password", "buy the book",
                     "Add a sentence to the page", "Delete the Mars article"):
            with self.subTest(text=text), self.assertRaises(BackendError) as caught:
                author.validate_request("wikipedia", text)
            self.assertEqual(caught.exception.code, "not_read_only")
        self.assertEqual(author.validate_request("python", "  Find the   newest release "), "Find the newest release")

    def test_a_plan_must_be_read_only_small_and_have_two_different_examples(self):
        author.validate_plan(plan())
        for bad in (plan(read_only=False), plan(outputs=[]), plan(goal=" "),
                    plan(params=[author.ParamSpec(name="Topic", example="a", alternate="b")]),
                    plan(params=[author.ParamSpec(name="topic", example="same", alternate="same")]),
                    plan(params=[author.ParamSpec(name="heading", example="a", alternate="b")])):
            with self.subTest(bad=bad), self.assertRaises(BackendError):
                author.validate_plan(bad)


class VetoTests(M2Harness):
    def test_only_typing_and_clicking_on_safe_controls_are_allowed(self):
        self.assertIsNone(author.veto("click", element("BUTTON", "Search"), "https://en.wikipedia.org/wiki/Main_Page"))
        self.assertIsNone(author.veto("done", None, "https://x"))
        for name in ("send_keys", "navigate", "switch", "upload_file"):
            self.assertIn("unsupported", author.veto(name, None, "https://x"))
        self.assertTrue(author.veto("input", element("TEXTAREA", "Notes"), "https://x"))
        self.assertTrue(author.veto("input", element(attributes={"type": "password"}), "https://x"))
        self.assertTrue(author.veto("click", element("BUTTON", "Publish changes"), "https://x"))
        self.assertTrue(author.veto("click", element("A", "Log in", attributes={"href": "/w/index.php?title=Special:UserLogin"}), "https://x"))
        self.assertTrue(author.veto("click", element("A", "Edit"), "https://x"))
        self.assertTrue(author.veto("click", element("BUTTON", "Search"), "https://en.wikipedia.org/w/index.php?title=A&action=edit"))


class CompileTests(M2Harness):
    def typed(self, text, el=None):
        return ({"input": {"index": 2, "text": text}}, el or element())

    def clicked(self, el=None):
        return ({"click": {"index": 3}}, el or element("BUTTON", "Search", backend_id=2))

    def test_typing_a_parameter_and_clicking_become_ordered_steps(self):
        captured = {(1, "html/body/1"): "#q", (2, "html/body/2"): "#go"}
        steps, fields = author.compile_steps(history(self.typed("Marie Curie"), self.clicked()), plan(), captured)
        self.assertEqual([(s["action_type"], s.get("param")) for s in steps], [("input", "topic"), ("click", None)])
        self.assertEqual(steps[0]["role"], "textbox")
        self.assertEqual(fields, {"input_search": "#q", "click_search": "#go"})

    def test_a_repeated_click_is_kept_once_and_unknown_typing_is_refused(self):
        captured = {(1, "html/body/1"): "#q", (2, "html/body/2"): "#go"}
        steps, _ = author.compile_steps(history(self.typed("Marie Curie"), self.clicked(), self.clicked()), plan(), captured)
        self.assertEqual(len(steps), 2)
        with self.assertRaises(BackendError) as caught:
            author.compile_steps(history(self.typed("something else"), self.clicked()), plan(), captured)
        self.assertEqual(caught.exception.code, "ambiguous_param")

    def test_frames_missing_selectors_and_unnamed_elements_are_refused(self):
        captured = {(1, "html/body/1"): "#q", (2, "html/body/2"): "#go"}
        for steps, selectors, code in (
                ([self.typed("Marie Curie", element(frame_id="f1")), self.clicked()], captured, "unsupported_action"),
                ([self.typed("Marie Curie"), self.clicked()], {(1, "html/body/1"): "#q"}, "unresolved_element"),
                ([self.typed("Marie Curie", element(name="")), self.clicked()], captured, "unresolved_element"),
                ([], captured, "unsupported_action")):
            with self.subTest(code=code), self.assertRaises(BackendError) as caught:
                author.compile_steps(history(*steps), plan(), selectors)
            self.assertEqual(caught.exception.code, code)

    def test_a_selector_that_embeds_an_example_value_is_caught(self):
        self.assertTrue(author.selectors_embed_values({"a": 'a[title="Marie Curie"]'}, plan()))
        self.assertTrue(author.selectors_embed_values({"a": "a[href*=grace hopper]"}, plan()))
        self.assertFalse(author.selectors_embed_values({"a": "#searchInput"}, plan()))


def sample_draft(workflow_id="custom-wikipedia-heading-ab12"):
    definition = {
        "goal": "Search for a topic and read the heading.",
        "steps": [{"field": "input_search", "action_type": "input", "label": "Search", "role": "textbox", "param": "topic"},
                  {"field": "click_search", "action_type": "click", "label": "Search", "role": "button"}],
        "outputs": {"heading": {"field": "read_heading", "read": "text"}},
        "params_schema": {"type": "object", "required": ["topic"], "additionalProperties": False,
                          "properties": {"topic": {"type": "string"}}},
        "output_schema": {"type": "object", "required": ["heading"], "additionalProperties": False,
                          "properties": {"heading": {"type": "string", "description": "the heading"}}},
        "canary": {"params": {"topic": "Marie Curie"}, "expected_output": {"heading": "Marie Curie"}}, "mutates": False}
    selector_map = {"workflow_id": workflow_id, "target_url": "https://en.wikipedia.org/wiki/Main_Page", "version": 1,
                    "fields": {"input_search": "#q", "click_search": "#go", "read_heading": "h1"}}
    return author.Draft(workflow_id, "wikipedia", "Read the heading", definition, selector_map, definition["steps"],
                        {"heading": "Marie Curie"}, 0.006, 15000)


class KeepingCreatedWorkflows(M2Harness):
    def post_draft(self, draft=None, error=None):
        mock = AsyncMock(return_value=draft or sample_draft(), side_effect=error)
        return patch("services.backend.author.draft", mock)

    async def create(self):
        with self.post_draft():
            reply = await self.client.post("/api/v1/workflows/draft", json={"site": "wikipedia", "request": "Read the heading"})
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()

    async def test_a_draft_is_previewed_then_kept_loaded_live_and_survives_a_restart(self):
        preview = await self.create()
        self.assertEqual(preview["steps"][0], {"action": "input", "label": "Search", "param": "topic"})
        self.assertEqual(preview["params"], [{"name": "topic", "example": "Marie Curie"}])
        self.assertEqual(preview["sample_output"], {"heading": "Marie Curie"})
        self.assertNotIn("custom-wikipedia-heading-ab12", [w["id"] for w in (await self.client.get("/api/v1/workflows")).json()])
        kept = await self.client.post(f"/api/v1/workflows/draft/{preview['id']}/accept")
        self.assertEqual(kept.status_code, 200, kept.text)
        self.assertEqual(kept.json()["id"], "custom-wikipedia-heading-ab12")
        self.assertIn("custom-wikipedia-heading-ab12", [w["id"] for w in (await self.client.get("/api/v1/workflows")).json()])
        self.assertTrue(custom.baseline_path(self.settings, "custom-wikipedia-heading-ab12").is_file())
        self.assertEqual((await self.client.post(f"/api/v1/workflows/draft/{preview['id']}/accept")).status_code, 404)
        restarted = create_app(self.settings)
        async with restarted.router.lifespan_context(restarted):
            self.assertIn("custom-wikipedia-heading-ab12", restarted.state.workflows)

    async def test_delete_removes_files_and_refuses_built_ins_and_busy_workflows(self):
        preview = await self.create()
        await self.client.post(f"/api/v1/workflows/draft/{preview['id']}/accept")
        self.assertEqual((await self.client.delete("/api/v1/workflows/sample-lookup")).status_code, 404)
        with patch.object(self.app.state.recovery, "active", return_value=True):
            self.assertEqual((await self.client.delete("/api/v1/workflows/custom-wikipedia-heading-ab12")).status_code, 409)
        self.assertEqual((await self.client.delete("/api/v1/workflows/custom-wikipedia-heading-ab12")).status_code, 200)
        self.assertNotIn("custom-wikipedia-heading-ab12", self.app.state.workflows)
        self.assertFalse((self.settings.workflows_dir / "custom-wikipedia-heading-ab12.json").exists())
        self.assertFalse(custom.baseline_path(self.settings, "custom-wikipedia-heading-ab12").exists())

    async def test_reset_all_restores_a_created_workflow_from_its_first_version(self):
        for command in (["init", "-q"], ["add", "contracts/selectors"],
                        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline"]):
            subprocess.run(["git", *command], cwd=self.root, check=True, capture_output=True)
        preview = await self.create()
        await self.client.post(f"/api/v1/workflows/draft/{preview['id']}/accept")
        path = self.settings.selectors_for("custom-wikipedia-heading-ab12")
        drifted = json.loads(path.read_text())
        drifted["fields"]["click_search"] = "#drifted"
        drifted["version"] = 4
        path.write_text(json.dumps(drifted))
        reply = await self.client.post("/api/v1/admin/reset")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(json.loads(path.read_text())["fields"]["click_search"], "#go")

    async def test_errors_map_to_statuses_and_quotas_and_busy_are_enforced(self):
        for code, status in (("not_read_only", 422), ("unresolved_element", 422), ("model_unconfigured", 503),
                             ("author_timeout", 504), ("agent_error", 502)):
            with self.subTest(code=code), self.post_draft(error=BackendError(code, "nope")):
                reply = await self.client.post("/api/v1/workflows/draft", json={"site": "wikipedia", "request": "Read the heading"})
                self.assertEqual((reply.status_code, reply.json()["detail"]["code"]), (status, code))
        self.assertFalse(self.app.state.author_busy)
        self.app.state.author_busy = True
        self.assertEqual((await self.client.post("/api/v1/workflows/draft", json={"site": "wikipedia", "request": "Read the heading"})).status_code, 409)
        self.app.state.author_busy = False
        self.app.state.drafts.created = [self.app.state.drafts.clock()] * custom.DRAFTS_PER_HOUR
        with self.post_draft():
            reply = await self.client.post("/api/v1/workflows/draft", json={"site": "wikipedia", "request": "Read the heading"})
        self.assertEqual((reply.status_code, reply.json()["detail"]["code"]), (422, "quota_hour"))

    async def test_expired_drafts_and_remote_callers_are_refused(self):
        preview = await self.create()
        self.app.state.drafts.clock = lambda: 10 ** 9
        self.assertEqual((await self.client.post(f"/api/v1/workflows/draft/{preview['id']}/accept")).status_code, 404)
        remote = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=("10.0.0.5", 1)), base_url="http://backend.test")
        self.addAsyncCleanup(remote.aclose)
        for method, path in (("post", "/api/v1/workflows/draft"), ("post", "/api/v1/workflows/draft/x/accept"),
                             ("delete", "/api/v1/workflows/custom-x")):
            kwargs = {"json": {"site": "wikipedia", "request": "Read the heading"}} if method == "post" and path.endswith("draft") else {}
            self.assertEqual((await getattr(remote, method)(path, **kwargs)).status_code, 403)
