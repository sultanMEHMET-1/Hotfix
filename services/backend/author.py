"""Turn one sentence into a read-only workflow on an allowlisted public site.

Pipeline: plan (one model call, no browser) -> agent run on the real site with a pre-action veto -> compile the
recorded typing and clicking into steps -> prove the result by replaying it with the real runner, with the example
values and again with alternate ones. Nothing is written to disk here; the caller decides whether to keep a draft.
"""

import asyncio
from dataclasses import dataclass, field, replace
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from uuid import uuid4

import sentry_sdk
from pydantic import BaseModel, Field, create_model

from contracts.api_types import WorkflowDefinition
from .config import BackendError, Settings, validator
from .healer import close_browser, load_browser_use, read_selector_expression, role, selector_expression
from .recovery import reads_match
from .runner import Runner

# Fixed start pages and hosts. The caller only ever names a site, never a URL.
SITES = {
    "wikipedia": ("Wikipedia", "https://en.wikipedia.org/wiki/Main_Page", "en.wikipedia.org"),
    "python": ("python.org", "https://www.python.org/", "www.python.org"),
}
NAME = r"^[a-z][a-z0-9_]{0,24}$"
MAX_STEPS = 6
ALLOWED_ACTIONS = {"input", "click", "done", "wait", "scroll"}
UNSAFE_NAME = re.compile(r"(?i)\b(publish|save changes|save page|log ?in|sign ?in|create account|donate|edit)\b")
# Words that mean the user wants something done, not read. Checked on the request itself, before any model call,
# because a model will happily rewrite "edit this article" into "read this article".
ACTION_WORDS = re.compile(
    r"(?i)\b(edit|add|change|update|delete|remove|create|post|publish|submit|send|upload|write|rewrite|replace|revert|"
    r"vandali[sz]e|log ?in|sign ?in|sign ?up|register|password|account|buy|purchase|order|pay|donate|subscribe|download and install)\b")
UNSAFE_URL = re.compile(r"(?i)action=(edit|submit)|veaction=edit|Special:(UserLogin|CreateAccount)")


class ParamSpec(BaseModel):
    name: str
    example: str
    alternate: str


class OutputSpec(BaseModel):
    name: str
    description: str


class Plan(BaseModel):
    read_only: bool
    goal: str
    params: list[ParamSpec] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)


@dataclass
class Draft:
    id: str
    site: str
    request: str
    definition: dict
    selector_map: dict
    steps: list[dict]
    sample_output: dict
    cost_usd: float | None = None
    duration_ms: float = 0
    warnings: list[str] = field(default_factory=list)


def slug(text, fallback="field"):
    cleaned = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:24].strip("_")
    return cleaned if cleaned and cleaned[0].isalpha() else fallback


def validate_request(site, request):
    if site not in SITES:
        raise BackendError("unknown_site", "Pick Wikipedia or python.org")
    request = " ".join((request or "").split())
    if not 5 <= len(request) <= 300:
        raise BackendError("bad_request", "Describe what you want in 5 to 300 characters")
    if ACTION_WORDS.search(request):
        raise BackendError("not_read_only", "Only requests that read information can be created")
    return request


def validate_plan(plan):
    if not plan.read_only:
        raise BackendError("not_read_only", "Only read-only requests can be created")
    if not plan.goal.strip() or not plan.outputs or len(plan.params) > 3 or len(plan.outputs) > 4:
        raise BackendError("bad_plan", "The request could not be turned into a small read-only task")
    names = [item.name for item in (*plan.params, *plan.outputs)]
    if any(not re.match(NAME, name) for name in names) or len(set(names)) != len(names):
        raise BackendError("bad_plan", "The request could not be turned into a small read-only task")
    for param in plan.params:
        if not param.example.strip() or not param.alternate.strip() or param.example.strip() == param.alternate.strip():
            raise BackendError("bad_plan", "Each variable input needs two different example values")
    return plan


async def make_plan(llm, site, request):
    from browser_use.llm import UserMessage
    name, url, _ = SITES[site]
    prompt = (
        f"Turn this request into a read-only browsing task on {name} ({url}).\nRequest: {request}\n"
        "Return: read_only (true only if the request, exactly as written, only asks to read information; false if any part of it "
        "would edit, create, delete, log in, buy, post or submit anything, even if a reading step could be extracted from it), "
        "goal (one imperative sentence that keeps the request's meaning), params (the variable inputs the user may change "
        "each time, at most 3: a snake_case name, an example value taken from the request, and a different alternate value "
        "of the same kind; empty if nothing varies), and outputs (what to read back, at most 4: a snake_case name and a "
        "short description of the value shown on the page).")
    reply = await llm.ainvoke([UserMessage(content=prompt)], output_format=Plan)
    return validate_plan(reply.completion)


def agent_task(plan, site):
    name, url, _ = SITES[site]
    examples = {param.name: param.example for param in plan.params}
    return (f"{plan.goal}\nStart on {url}. Use these values for the variable inputs: {json.dumps(examples)}.\n"
            "Rules: this is a read-only task. Only type into fields and click links or buttons, one action at a time. "
            "Do not press keys, open tabs, type a URL, or click a suggestion in a dropdown: click the page's own Search "
            "or GO button. Never edit anything, log in, create an account, or submit a form other than a search. If a "
            "login, captcha or access wall appears, stop and report failure. When you finish, report exactly as the page "
            "shows them: " + ", ".join(f"{o.name} ({o.description})" for o in plan.outputs) + ".")


def veto(action_name, element, url):
    """Return a reason to stop before this action runs, or None."""
    if action_name not in ALLOWED_ACTIONS:
        return f"unsupported action {action_name}"
    if UNSAFE_URL.search(url or ""):
        return "the page is an edit or login page"
    if element:
        attrs = element.get("attributes") or {}
        if element.get("node_name") == "TEXTAREA" or attrs.get("type") in {"password", "file"}:
            return "a text area or secret field"
        if UNSAFE_URL.search(attrs.get("href") or "") or UNSAFE_NAME.search(element.get("ax_name") or ""):
            return "an edit, publish or login control"
    return None


def compile_steps(serialized, plan, captured):
    """Map the agent's recorded typing and clicking to workflow steps and the selector map's step fields."""
    examples = {param.example.strip(): param.name for param in plan.params}
    steps, fields, keys = [], {}, []
    for entry in serialized.get("history", []):
        actions = (entry.get("model_output") or {}).get("action", [])
        results = entry.get("result") or []
        elements = (entry.get("state") or {}).get("interacted_element") or []
        for index, action in enumerate(actions):
            kind = next(iter(action), None)
            if kind not in {"input", "click"} or index >= len(results) or index >= len(elements):
                continue
            result, element = results[index], elements[index]
            if not result or result.get("error") or not element:
                continue
            if element.get("frame_id"):
                raise BackendError("unsupported_action", "The page uses a frame, which cannot be recorded")
            key = (element["backend_node_id"], element["x_path"])
            selector = captured.get(key)
            if not selector:
                raise BackendError("unresolved_element", "No unique selector was verified for an element the agent used")
            label = element.get("ax_name")
            if not label:
                raise BackendError("unresolved_element", "An element the agent used has no accessible name")
            param = None
            if kind == "input":
                param = examples.get((action["input"].get("text") or "").strip())
                if param is None:
                    raise BackendError("ambiguous_param", "The agent typed a value that is not one of the variable inputs")
            if keys and keys[-1] == (kind, key):  # the agent repeated itself: keep the latest
                steps.pop()
                fields.pop(next(reversed(fields)))
                keys.pop()
            base = f"{'input' if kind == 'input' else 'click'}_{slug(label)}"
            name, n = base, 2
            while name in fields:
                name, n = f"{base}_{n}", n + 1
            step = {"field": name, "action_type": kind, "label": label}
            if role(element):
                step["role"] = role(element)
            if param:
                step["param"] = param
            steps.append(step)
            fields[name] = selector
            keys.append((kind, key))
    if not steps or len(steps) > MAX_STEPS:
        raise BackendError("unsupported_action", "The agent did not complete the task by typing and clicking")
    return steps, fields


def make_temp_root(settings, workflow_id, definition, selector_map):
    root = Path(tempfile.mkdtemp(prefix="author-"))
    contracts = root / "contracts"
    (contracts / "workflows").mkdir(parents=True)
    (contracts / "selectors").mkdir()
    for schema in (settings.root / "contracts").glob("*.schema.json"):
        shutil.copy(schema, contracts / schema.name)
    (contracts / "workflows" / f"{workflow_id}.json").write_text(json.dumps(definition))
    (contracts / "selectors" / f"{workflow_id}.json").write_text(json.dumps(selector_map))
    return root


async def verify(settings, workflow_id, definition, selector_map, plan, reported, deadline):
    """Prove the workflow with the real runner: the example values, again, and the alternate values."""
    root = make_temp_root(settings, workflow_id, definition, selector_map)
    try:
        runner = Runner(replace(settings, root=root, runner_script=settings.script))
        output_validator = validator(definition["output_schema"])
        examples = {param.name: param.example for param in plan.params}
        alternates = {param.name: param.alternate for param in plan.params}

        async def replay(params):
            result = await runner.execute(workflow_id, params, output_validator, deadline=deadline)
            if result.data is None:
                step = result.failure.failed_step if result.failure else (result.error.code if result.error else "unknown")
                raise BackendError("replay_failed", f"The recorded workflow did not run again (stopped at {step})")
            return result.data

        first = await replay(examples)
        if not reads_match(first, reported):
            raise BackendError("replay_mismatch", "The recorded workflow read something other than the agent reported")
        if await replay(examples) != first:
            raise BackendError("replay_unstable", "The page gave different answers for the same request")
        if alternates:
            other = await replay(alternates)
            if other == first:
                raise BackendError("output_ignores_param", "Changing the input did not change the answer")
        return first
    finally:
        shutil.rmtree(root, ignore_errors=True)


def selectors_embed_values(fields, plan):
    values = [v.strip().lower() for param in plan.params for v in (param.example, param.alternate) if len(v.strip()) >= 3]
    return any(value in selector.lower() for selector in fields.values() for value in values)


async def draft(settings: Settings, site: str, request: str, *, timeout: float = 120) -> Draft:
    request = validate_request(site, request)
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")
    if not key or not model:
        raise BackendError("model_unconfigured", "Set GOOGLE_API_KEY and GEMINI_MODEL to create workflows")
    clock = asyncio.get_running_loop().time
    started = clock()
    deadline = started + timeout
    workdirs = [tempfile.mkdtemp(prefix="author-profile-"), tempfile.mkdtemp(prefix="author-files-")]
    browser = llm = None
    vetoed = {}
    try:
        async with asyncio.timeout(timeout):
            Agent, BrowserSession, ChatGoogle, DOMInteractedElement = await asyncio.to_thread(load_browser_use)
            llm = ChatGoogle(model=model, api_key=key, max_retries=1)
            with sentry_sdk.start_span(op="author.plan", name="author.plan"):
                plan = await make_plan(llm, site, request)
            _, url, host = SITES[site]
            browser = BrowserSession(headless=settings.headless, executable_path=settings.browser_executable,
                                     enable_default_extensions=False, keep_alive=True,
                                     user_data_dir=workdirs[0], allowed_domains=[host])
            captured = {}
            agent = None

            async def capture(state, output, step_number):
                for action in output.action:
                    dump = action.model_dump(exclude_none=True)
                    name = next(iter(dump), "")
                    index = action.get_index()
                    node = state.dom_state.selector_map.get(index) if index is not None else None
                    element = DOMInteractedElement.load_from_enhanced_dom_tree(node).to_dict() if node is not None else None
                    reason = veto(name, element, getattr(state, "url", ""))
                    if reason:
                        vetoed["reason"] = reason
                        agent.stop()
                        raise BackendError("unsafe_action", f"Stopped before an unsafe action: {reason}")
                    if element and not element.get("frame_id") and name in {"input", "click"}:
                        cdp = await browser.get_or_create_cdp_session()
                        response = await cdp.cdp_client.send.Runtime.evaluate(
                            params={"expression": selector_expression(element), "returnByValue": True}, session_id=cdp.session_id)
                        value = response.get("result", {}).get("value")
                        if value:
                            captured[(element["backend_node_id"], element["x_path"])] = value

            reading = create_model("Reading", **{o.name: (str, Field(description=o.description)) for o in plan.outputs})
            agent = Agent(task=agent_task(plan, site), llm=llm, browser_session=browser,
                          initial_actions=[{"navigate": {"url": url, "new_tab": False}}],
                          register_new_step_callback=capture, max_actions_per_step=1, use_judge=False,
                          calculate_cost=True, enable_signal_handler=False, max_failures=1, enable_planning=False,
                          message_compaction=False, llm_timeout=min(30, timeout), file_system_path=workdirs[1],
                          output_model_schema=reading)
            with sentry_sdk.start_span(op="author.agent", name="author.agent"):
                history = await agent.run(max_steps=8)
            if vetoed:
                raise BackendError("unsafe_action", f"Stopped before an unsafe action: {vetoed['reason']}")
            if history is None or getattr(history, "is_successful", lambda: None)() is False:
                raise BackendError("agent_blocked", "The agent could not complete the task, for example behind a login wall")
            structured = history.structured_output
            reported = {o.name: " ".join(str(getattr(structured, o.name, "") or "").split()) for o in plan.outputs}
            if not all(reported.values()):
                raise BackendError("agent_no_result", "The agent did not report every value")
            serialized = history.model_dump()
            steps, fields = compile_steps(serialized, plan, captured)
            cdp = await browser.get_or_create_cdp_session()
            outputs = {}
            for output in plan.outputs:
                response = await cdp.cdp_client.send.Runtime.evaluate(
                    params={"expression": read_selector_expression([reported[output.name]], forgiving=True), "returnByValue": True},
                    session_id=cdp.session_id)
                found = response.get("result", {}).get("value") or {}
                if found.get("count") != 1 or not found.get("selector"):
                    raise BackendError("unresolved_element", f"No single element shows the value for {output.name}")
                reported[output.name] = found["text"]  # the value as the page shows it, even if the agent shortened it
                outputs[output.name] = (f"read_{output.name}", found["selector"])
            fields.update(dict(outputs.values()))
            if selectors_embed_values(fields, plan):
                raise BackendError("param_in_selector", "A selector contains one of the example values")
            usage = history.usage
            cost = usage.total_cost if usage and usage.entry_count and math.isfinite(usage.total_cost) and usage.total_cost > 0 else None

            words = re.sub(r"[^a-z0-9]+", "-", plan.goal.lower()).strip("-")[:20].strip("-") or "task"
            workflow_id = f"custom-{site}-{words}-{uuid4().hex[:4]}"  # ids are lowercase words joined by hyphens
            string = {"type": "string"}
            definition = {
                "goal": plan.goal, "steps": steps,
                "outputs": {o.name: {"field": outputs[o.name][0], "read": "text"} for o in plan.outputs},
                "params_schema": {"type": "object", "required": [p.name for p in plan.params], "additionalProperties": False,
                                  "properties": {p.name: string for p in plan.params}},
                "output_schema": {"type": "object", "required": [o.name for o in plan.outputs], "additionalProperties": False,
                                  "properties": {o.name: {**string, "description": o.description} for o in plan.outputs}},
                "canary": {"params": {p.name: p.example.strip() for p in plan.params}, "expected_output": reported},
                "mutates": False,
            }
            WorkflowDefinition.model_validate(definition)
            selector_map = {"workflow_id": workflow_id, "target_url": url, "version": 1, "fields": fields}
            with sentry_sdk.start_span(op="author.verify", name="author.verify"):
                sample = await verify(settings, workflow_id, definition, selector_map, plan, reported, deadline)
            return Draft(workflow_id, site, request, definition, selector_map, steps, sample, cost,
                         (clock() - started) * 1000)
    except TimeoutError as exc:
        raise BackendError("author_timeout", "Creating the workflow took too long") from exc
    except BackendError:
        raise
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        raise BackendError("agent_error", "Creating the workflow failed") from exc
    finally:
        try:
            if browser:
                await close_browser(browser)
        finally:
            client = getattr(llm, "_client", None)
            if client is not None:
                try:
                    await asyncio.wait_for(client.aio.aclose(), timeout=3)
                    await asyncio.wait_for(asyncio.to_thread(client.close), timeout=3)
                except Exception:
                    pass
            for workdir in workdirs:
                shutil.rmtree(workdir, ignore_errors=True)
