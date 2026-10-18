"""Workflows created from a sentence: keeping a draft, saving it, loading it live, and removing it.

They are ordinary workflows (a definition plus a selector map) whose ids start with `custom-`, written next to the
built-in ones but ignored by git. A first-version snapshot of the map is kept so Reset can restore it.
"""

import json
import os
from pathlib import Path
import time
from uuid import uuid4

from .config import BackendError, Settings, load_workflow, referenced_fields
from .store import SelectorStore

DRAFT_TTL_S = 900
DRAFTS_PER_HOUR = 5
MAX_CUSTOM = 20


def baseline_path(settings: Settings, workflow_id: str) -> Path:
    return settings.root / "state/custom-baselines" / f"{workflow_id}.json"


def custom_ids(app):
    return sorted(name for name in app.state.workflows if name.startswith("custom-"))


class Drafts:
    """Drafts waiting to be kept or discarded, in memory only, plus the hour's creation count for the quota."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.items = {}
        self.created = []

    def prune(self):
        now = self.clock()
        self.items = {token: (expires, draft) for token, (expires, draft) in self.items.items() if expires > now}
        self.created = [at for at in self.created if now - at < 3600]

    def check_quota(self, app):
        self.prune()
        if len(self.created) >= DRAFTS_PER_HOUR:
            raise BackendError("quota_hour", f"At most {DRAFTS_PER_HOUR} workflows can be created per hour")
        if len(custom_ids(app)) >= MAX_CUSTOM:
            raise BackendError("quota_total", f"At most {MAX_CUSTOM} created workflows can be kept; delete one first")

    def count_attempt(self):
        """Every attempt that could have spent model money counts toward the hourly quota, kept or not."""
        self.created.append(self.clock())

    def add(self, draft):
        token = uuid4().hex[:12]
        self.items[token] = (self.clock() + DRAFT_TTL_S, draft)
        return token

    def get(self, token):
        self.prune()
        entry = self.items.get(token)
        return entry[1] if entry else None

    def discard(self, token):
        self.items.pop(token, None)


def write_atomic(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(temporary, path)


def register(app, settings: Settings, workflow_id: str):
    """Load one workflow from disk into the running app, with the same checks startup applies."""
    triple = load_workflow(settings.workflows_dir / f"{workflow_id}.json")
    store = SelectorStore(settings, workflow_id)
    selector_map = store.read()
    if selector_map["workflow_id"] != workflow_id or not referenced_fields(triple[0]) <= set(selector_map["fields"]):
        raise ValueError("The selector map does not match the workflow")
    app.state.workflows[workflow_id] = triple
    app.state.stores[workflow_id] = store


def keep(app, settings: Settings, draft):
    """Write a draft's files (map first, so a crash never leaves a definition without one) and load it live."""
    paths = [baseline_path(settings, draft.id), settings.selectors_for(draft.id), settings.workflows_dir / f"{draft.id}.json"]
    try:
        write_atomic(paths[0], draft.selector_map)
        write_atomic(paths[1], draft.selector_map)
        write_atomic(paths[2], draft.definition)
        register(app, settings, draft.id)
    except Exception:
        app.state.workflows.pop(draft.id, None)
        app.state.stores.pop(draft.id, None)
        for path in reversed(paths):
            path.unlink(missing_ok=True)
        raise


def remove(app, settings: Settings, workflow_id: str):
    """Forget a created workflow and delete its files (definition first, so a crash leaves nothing startup would load)."""
    app.state.workflows.pop(workflow_id, None)
    app.state.stores.pop(workflow_id, None)
    app.state.recovery.cooldown.pop(workflow_id, None)
    for path in (settings.workflows_dir / f"{workflow_id}.json", settings.selectors_for(workflow_id),
                 baseline_path(settings, workflow_id), settings.root / "state" / f"{workflow_id}.lock"):
        path.unlink(missing_ok=True)


def view(token, draft):
    definition = draft.definition
    return {
        "id": token, "workflow_id": draft.id, "site": draft.site, "request": draft.request, "goal": definition["goal"],
        "steps": [{"action": step["action_type"], "label": step.get("label"), "param": step.get("param")}
                  for step in draft.steps],
        "params": [{"name": name, "example": definition["canary"]["params"][name]}
                   for name in definition["params_schema"]["required"]],
        "outputs": [{"name": name, "description": definition["output_schema"]["properties"][name].get("description", "")}
                    for name in definition["outputs"]],
        "sample_output": draft.sample_output, "cost_usd": draft.cost_usd, "duration_ms": draft.duration_ms,
        "warnings": draft.warnings,
    }
