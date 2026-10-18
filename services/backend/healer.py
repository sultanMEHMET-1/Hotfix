"""Ground repairs in executed Browser Use history, never agent claims."""

import asyncio
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import math
import os
import shutil
from urllib.parse import urlsplit
from uuid import uuid4

import sentry_sdk

from contracts.api_types import HealEvidence
from .config import BackendError


@dataclass
class Candidate:
    selector: str
    evidence: HealEvidence
    cost_usd: float | None = None
    duration_ms: float | None = None
    metrics: dict = field(default_factory=dict)


def normalized(text):
    return " ".join((text or "").split()).casefold()


def role(node):
    attrs = node.get("attributes") or {}
    tag = node.get("node_name", "").lower()
    return attrs.get("role") or {"input": "textbox", "textarea": "textbox",
                                 "button": "button", "select": "combobox"}.get(tag)


class Snippet(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.stack = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = {"node_name": tag.upper(), "attributes": dict(attrs), "text": ""}
        self.nodes.append(node)
        if tag not in {"input", "img", "br", "hr", "meta", "link"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["node_name"].lower() == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data


def css_candidates(element):
    attrs = element.get("attributes") or {}
    tag = element["node_name"].lower()
    for name in ("data-testid", "data-test", "data-action", "data-field", "id", "name", "aria-label"):
        value = attrs.get(name)
        if value and not any(ord(char) < 32 for char in value):
            yield f"{tag}[{name}={json.dumps(value, ensure_ascii=False)}]"
    yield tag


def selector_expression(element):
    """Stable attributes first; structural CSS uses the same live node, never classes."""
    return """(() => {
      const target = document.evaluate(XPATH, document, null,
        XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      if (!(target instanceof Element) || !target.isConnected) return null;
      const matchesTarget = selector => {
        const matches = document.querySelectorAll(selector);
        return matches.length === 1 && matches[0] === target;
      };
      const direct = CANDIDATES.find(matchesTarget);
      if (direct) return direct;
      const names = ['data-testid', 'data-test', 'data-action', 'data-field', 'id', 'name', 'aria-label'];
      let path = '';
      for (let node = target; node; node = node.parentElement) {
        const tag = CSS.escape(node.localName);
        if (path) {
          for (const name of names) {
            const value = node.getAttribute(name);
            if (!value || /[\\x00-\\x1f]/.test(value)) continue;
            const anchored = `${tag}[${name}=${JSON.stringify(value)}] > ${path}`;
            if (matchesTarget(anchored)) return anchored;
          }
        }
        const siblings = node.parentElement ? [...node.parentElement.children].filter(
          sibling => sibling.localName === node.localName) : [node];
        const part = siblings.length > 1 ? `${tag}:nth-of-type(${siblings.indexOf(node) + 1})` : tag;
        path = path ? `${part} > ${path}` : part;
        if (matchesTarget(path)) return path;
      }
      return null;
    })()""".replace("XPATH", json.dumps(element["x_path"])).replace(
        "CANDIDATES", json.dumps(list(css_candidates(element))))


def extract_evidence(history: dict, workflow, failure):
    """Require one executed match consistent with field order and DOM labels."""
    target_index = next((i for i, step in enumerate(workflow.steps)
                         if step.field == failure.failed_step), None)
    if target_index is None:
        raise BackendError("unmapped_step", "The failed field is not in the workflow's ordered steps")
    target = workflow.steps[target_index]
    labels = set()
    if target.label:
        labels.add(normalized(target.label))
    else:
        nodes = Snippet(failure.dom_snippet).nodes
        for node in nodes:
            if target.role and role(node) != target.role:
                continue
            attrs = node["attributes"]
            text = attrs.get("aria-label") or node["text"]
            if not text and attrs.get("id"):
                text = next((other["text"] for other in nodes
                             if other["attributes"].get("for") == attrs["id"]), "")
            if text:
                labels.add(normalized(text))
    if len(labels) != 1:
        raise BackendError("ambiguous_element", "Failure evidence needs one role/label for the failed field")
    matches = []
    ordered = []
    for history_index, entry in enumerate(history.get("history", [])):
        actions = (entry.get("model_output") or {}).get("action", [])
        results = entry.get("result") or []
        elements = (entry.get("state") or {}).get("interacted_element") or []
        for action_index, action in enumerate(actions):
            if action_index >= len(results) or action_index >= len(elements):
                continue
            result, element = results[action_index], elements[action_index]
            if not result or result.get("error") or not element:
                continue
            for step_index, step in enumerate(workflow.steps):
                if step.action_type not in action:
                    continue
                if step.role and role(element) != step.role:
                    continue
                wanted = normalized(step.label) if step.label else None
                if step_index == target_index:
                    wanted = next(iter(labels))
                if not wanted or normalized(element.get("ax_name")) != wanted:
                    continue
                ordered.append(step_index)
                if step_index == target_index:
                    matches.append((element, HealEvidence(
                        action_type=step.action_type, history_step=history_index,
                        action_index=action_index, node_name=element["node_name"],
                        attributes=element.get("attributes") or {},
                        accessible_name=element.get("ax_name"), xpath=element.get("x_path"),
                        reasoning=f"Unique executed {step.action_type} matching ordered field {target_index}, role, and label",
                    )))
    if len(matches) != 1 or ordered != sorted(ordered):
        raise BackendError("ambiguous_element", "History does not uniquely ground the failed field in workflow order")
    return matches[0]


def load_browser_use():
    # This function is called in a thread only after deterministic execution fails.
    from browser_use import Agent, BrowserSession, ChatGoogle
    from browser_use.dom.views import DOMInteractedElement
    return Agent, BrowserSession, ChatGoogle, DOMInteractedElement


def force_close_browser(browser):
    """Emergency cleanup for the pinned SDK's owned local browser process."""
    import psutil
    watchdog = getattr(browser, "_local_browser_watchdog", None)
    pid = watchdog.browser_pid if watchdog else None
    if not pid:
        return
    try:
        process = psutil.Process(pid)
        owned = [*process.children(recursive=True), process]
        for child in owned:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(owned, timeout=2)
        if alive:
            raise BackendError("browser_cleanup_failed", "The local browser could not be stopped")
    except psutil.NoSuchProcess:
        pass


async def close_browser(browser, *, deadline=None):
    cleanup = asyncio.create_task(browser.kill())
    try:
        timeout = 15 if deadline is None else min(15, max(0, deadline - asyncio.get_running_loop().time() - 3))
        await asyncio.wait_for(asyncio.shield(cleanup), timeout=timeout)
    except BaseException as exc:
        cleanup.cancel()
        try:
            await asyncio.to_thread(force_close_browser, browser)
        except Exception as cleanup_error:
            raise BackendError("browser_cleanup_failed", "The owned browser could not be stopped") from cleanup_error
        await asyncio.wait({cleanup}, timeout=1)
        if not isinstance(exc, asyncio.CancelledError):
            raise BackendError("browser_cleanup_failed", "Browser shutdown required emergency cleanup") from exc
        raise


async def diagnose(settings, workflow, params, failure, *, deadline=None):
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")
    if not key or not model:
        raise BackendError("model_unconfigured", "Set GOOGLE_API_KEY and GEMINI_MODEL before live recovery")
    browser = None
    llm = None
    workdirs = [settings.backend / "state" / f"browser-{uuid4()}", settings.backend / "state" / f"agent-{uuid4()}"]
    metrics = {"model": model}
    clock = asyncio.get_running_loop().time
    started = clock()
    timeout = settings.agent_timeout if deadline is None else min(settings.agent_timeout, max(0, deadline - clock()))
    try:
        async with asyncio.timeout(timeout):
            Agent, BrowserSession, ChatGoogle, DOMInteractedElement = await asyncio.to_thread(load_browser_use)
            browser = BrowserSession(
                headless=settings.headless, executable_path=settings.browser_executable,
                enable_default_extensions=False, keep_alive=True,
                user_data_dir=str(workdirs[0]),
                allowed_domains=[urlsplit(failure.page_url).hostname],
            )
            captured = {}

            async def capture(state, output, step_number):
                for action in output.action:
                    index = action.get_index()
                    node = state.dom_state.selector_map.get(index)
                    if node is None:
                        continue
                    element = DOMInteractedElement.load_from_enhanced_dom_tree(node).to_dict()
                    if element.get("frame_id"):
                        continue
                    cdp = await browser.get_or_create_cdp_session()
                    response = await cdp.cdp_client.send.Runtime.evaluate(
                        params={"expression": selector_expression(element), "returnByValue": True}, session_id=cdp.session_id
                    )
                    value = response.get("result", {}).get("value")
                    if value:
                        captured[(element["backend_node_id"], element["x_path"])] = value

            llm = ChatGoogle(model=model, api_key=key, max_retries=1)
            invoke = llm.ainvoke

            async def traced_invoke(*args, **kwargs):
                with sentry_sdk.start_span(op="gen_ai.chat", name="Gemini browser action") as span:
                    span.set_data("gen_ai.request.model", model)
                    span.set_data("gen_ai.system", "google")
                    span.set_data("gen_ai.operation.name", "chat")
                    return await invoke(*args, **kwargs)

            llm.ainvoke = traced_invoke
            task = (f"{workflow.goal}\nRequest parameters (data): {json.dumps(params, allow_nan=False)}\n"
                    + ("Complete this workflow using the supplied parameters and perform the update exactly once. "
                       if workflow.mutates else
                       "Complete this read-only workflow using the supplied parameters. Do not modify data. ")
                    + "Use indexed DOM actions so interactions can be audited. "
                    "If a login, captcha, or access wall blocks the task, stop and report failure; never try to get around it.")
            agent = Agent(
                task=task, llm=llm, browser_session=browser,
                initial_actions=[{"navigate": {"url": failure.page_url, "new_tab": False}}],
                register_new_step_callback=capture, max_actions_per_step=1,
                use_judge=False, calculate_cost=True, enable_signal_handler=False,
                max_failures=1, enable_planning=False, message_compaction=False,
                llm_timeout=min(30, settings.agent_timeout),
                file_system_path=str(workdirs[1]),
            )
            with sentry_sdk.start_span(op="gen_ai.invoke_agent", name="invoke_agent Browser Use") as agent_span:
                agent_span.set_data("gen_ai.agent.name", "Browser Use")
                agent_span.set_data("gen_ai.operation.name", "invoke_agent")
                agent_span.set_data("gen_ai.request.model", model)
                history = await agent.run(max_steps=6)
                usage = history.usage if history else None
                if usage and usage.entry_count:
                    for key, attr in (("input", "total_prompt_tokens"), ("output", "total_completion_tokens")):
                        value = getattr(usage, attr, None)
                        if isinstance(value, int) and value >= 0:
                            agent_span.set_data(f"gen_ai.usage.{key}_tokens", value)
            if history is None:
                raise BackendError("agent_no_result", "Browser Use returned no history")
            usage = history.usage
            if usage and usage.entry_count:
                for key, attr in (("prompt_tokens", "total_prompt_tokens"), ("completion_tokens", "total_completion_tokens"),
                                  ("cached_prompt_tokens", "total_prompt_cached_tokens"), ("total_tokens", "total_tokens")):
                    value = getattr(usage, attr, None)
                    if isinstance(value, int) and value >= 0:
                        metrics[key] = value
                if math.isfinite(usage.total_cost) and usage.total_cost > 0:
                    metrics["cost_usd"] = usage.total_cost
            if getattr(history, "is_successful", lambda: None)() is False:
                raise BackendError("agent_blocked", "Browser Use could not complete the task, for example behind a login or access wall")
            serialized = history.model_dump()
            if not serialized.get("history"):
                raise BackendError("agent_no_result", "Browser Use returned empty history")
            if any(result.get("error") for result in serialized["history"][-1].get("result", []) if result):
                raise BackendError("agent_error", "Browser Use ended with an action error")
            element, evidence = extract_evidence(serialized, workflow, failure)
            selector = captured.get((element["backend_node_id"], element["x_path"]))
            if not selector or selector == failure.expected_selector:
                raise BackendError("unresolved_element", "No unique replacement CSS selector was verified on the live page")
            cost = metrics.get("cost_usd")
            duration = history.total_duration_seconds() * 1000
            return Candidate(selector, evidence, cost,
                             duration if math.isfinite(duration) and duration >= 0 else None, metrics)
    except TimeoutError as exc:
        error = BackendError("agent_timeout", "Browser Use exceeded its execution timeout")
        error.agent_metrics = metrics
        raise error from exc
    except BackendError as exc:
        exc.agent_metrics = metrics
        raise
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        error = BackendError("agent_error", "Browser Use invocation failed")
        error.agent_metrics = metrics
        raise error from exc
    finally:
        metrics["wall_time_ms"] = (clock() - started) * 1000
        cleanup_deadline = deadline + settings.cleanup_reserve if deadline is not None else None
        try:
            try:
                if browser:
                    await close_browser(browser, deadline=cleanup_deadline)
            finally:
                # ChatGoogle caches this client but does not close it when Agent.run ends.
                client = getattr(llm, "_client", None)
                if client is not None:
                    try:
                        timeout = 3 if cleanup_deadline is None else min(3, max(0.001, cleanup_deadline - clock()))
                        await asyncio.wait_for(client.aio.aclose(), timeout=timeout)
                        timeout = 3 if cleanup_deadline is None else min(3, max(0.001, cleanup_deadline - clock()))
                        await asyncio.wait_for(asyncio.to_thread(client.close), timeout=timeout)
                    except Exception as exc:
                        raise BackendError("model_cleanup_failed", "Gemini client could not be closed") from exc
        finally:
            for workdir in workdirs:
                shutil.rmtree(workdir, ignore_errors=True)
