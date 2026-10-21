"""Verified first run: a workflow listed in BUILD_ON_FIRST_RUN starts "unbuilt".

Its first successful run is checked by a real Browser Use agent that opens the same page and reports what it
shows. Only when those values match what the deterministic runner read is the endpoint marked built; every later
run is the fast path with no model. The agent verifies the selectors, it does not discover them.
"""

import asyncio
import importlib.util
import json
import os
import re
import shutil
import sys
from urllib.parse import urlsplit
from uuid import uuid4

import sentry_sdk
from pydantic import Field, create_model

from .config import BackendError

# ponytail: a fixed set, also the workflows whose typed input gets the bad-input guard. Move it into the
# workflow definition if a third site needs it.
BUILD_ON_FIRST_RUN = {"ucla-class-status"}


def marker(settings, workflow_id):
    return settings.backend / "state" / f"built-{workflow_id}.json"


def is_built(settings, workflow_id):
    return workflow_id not in BUILD_ON_FIRST_RUN or marker(settings, workflow_id).is_file()


def mark_built(settings, workflow_id, **evidence):
    path = marker(settings, workflow_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence) + "\n")


def clear(settings, workflow_id):
    marker(settings, workflow_id).unlink(missing_ok=True)


def page_url(settings, selectors, params):
    """The page the runner opened: the map's target_url with its placeholders filled by the runner's own function."""
    module = sys.modules.get("mender_runner_execute")
    if module is None:  # registered before it runs: the runner's dataclass looks its own module up
        spec = importlib.util.spec_from_file_location("mender_runner_execute", settings.script)
        module = sys.modules["mender_runner_execute"] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module.expand_url(selectors["target_url"], params)


def same(read, reported):
    """Case and punctuation do not matter: the agent may join a multi-line cell with a different separator."""
    squash = lambda text: re.sub(r"[^a-z0-9]+", "", str(text).casefold())
    return all(squash(read.get(key, "")) == squash(value) for key, value in reported.items())


async def verify(settings, workflow, url, data):
    """Run the agent on `url`; raise unless it reports the values the runner read. Returns (cost_usd, duration_ms)."""
    from .healer import close_browser, load_browser_use  # here, so importing the app never loads the model code
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")
    if not key or not model:
        raise BackendError("model_unconfigured", "Set GOOGLE_API_KEY and GEMINI_MODEL to build this endpoint")
    keys = list(workflow.outputs)
    described = ", ".join(f"{k} ({workflow.output_schema['properties'][k].get('description') or k})" for k in keys)
    browser = llm = None
    workdirs = [settings.backend / "state" / f"browser-{uuid4()}", settings.backend / "state" / f"agent-{uuid4()}"]
    try:
        async with asyncio.timeout(settings.agent_timeout):
            Agent, BrowserSession, ChatGoogle, _ = await asyncio.to_thread(load_browser_use)
            browser = BrowserSession(headless=settings.headless, executable_path=settings.browser_executable,
                                     enable_default_extensions=False, keep_alive=True, user_data_dir=str(workdirs[0]),
                                     allowed_domains=[urlsplit(url).hostname])
            llm = ChatGoogle(model=model, api_key=key, max_retries=1)
            agent = Agent(
                task=(f"{workflow.goal}\nThe results page is already open. This is read-only: do not click anything that changes data. "
                      "Report exactly as the page displays it, for the first section listed, the values of: " + described + ". "
                      "If a login, captcha, or access wall blocks the task, stop and report failure."),
                llm=llm, browser_session=browser, initial_actions=[{"navigate": {"url": url, "new_tab": False}}],
                max_actions_per_step=1, use_judge=False, calculate_cost=True, enable_signal_handler=False, max_failures=1,
                enable_planning=False, message_compaction=False, llm_timeout=min(30, settings.agent_timeout),
                file_system_path=str(workdirs[1]),
                output_model_schema=create_model("Reading", **{k: (str, Field(description=f"The {k} value shown on the page")) for k in keys}))
            with sentry_sdk.start_span(op="gen_ai.invoke_agent", name="invoke_agent Browser Use (build)") as span:
                span.set_data("gen_ai.agent.name", "Browser Use")
                span.set_data("gen_ai.request.model", model)
                history = await agent.run(max_steps=6)
        if history is None or getattr(history, "is_successful", lambda: None)() is False:
            raise BackendError("agent_blocked", "Browser Use could not read the page, for example behind a login or access wall")
        structured = history.structured_output
        reported = {k: " ".join(str(getattr(structured, k, "") or "").split()) for k in keys} if structured else {}
        if not all(reported.values()):
            raise BackendError("agent_no_result", "Browser Use did not report the values shown on the page")
        if not same(data, reported):
            raise BackendError("build_mismatch", "The agent read different values than the selectors did, so the endpoint was not marked built")
        usage = history.usage
        cost = usage.total_cost if usage and usage.entry_count and usage.total_cost > 0 else None
        return cost, history.total_duration_seconds() * 1000
    except TimeoutError as exc:
        raise BackendError("agent_timeout", "Browser Use exceeded its execution timeout") from exc
    except BackendError:
        raise
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        raise BackendError("agent_error", "Browser Use invocation failed") from exc
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
