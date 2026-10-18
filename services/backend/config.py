"""Backend-owned workflow definitions and runtime configuration."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlsplit

import jsonschema

from contracts.api_types import WorkflowDefinition


class BackendError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def read_json(path: Path):
    def reject_constant(value):
        raise ValueError(f"Non-JSON numeric constant: {value}")

    return json.loads(path.read_text(), parse_constant=reject_constant)


def validator(schema: dict):
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema, format_checker=jsonschema.FormatChecker())


# The definition model is shared with every other service through the contracts package.
Workflow = WorkflowDefinition


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def default_runner_python(root: Path):
    """The project venv (made by services/runner/setup_venv.sh) has Playwright; the backend's own interpreter does not."""
    venv = root / ".venv/bin/python"
    return str(venv) if venv.is_file() else sys.executable


def write_allowed(url: str, extra_hosts=()):
    """Mutating workflows may only touch sites we control: loopback or an explicit allowlist."""
    return (urlsplit(url).hostname or "") in LOCAL_HOSTS | set(extra_hosts)


@dataclass
class Settings:
    root: Path
    runner_script: Path | None = None
    runner_python: str = sys.executable
    runner_timeout: float = 45
    agent_timeout: float = 90
    recovery_timeout: float = 240
    cleanup_reserve: float = 30
    lock_timeout: float = 5
    failure_cooldown: float = 15
    write_hosts: tuple = ()
    demo_workflow: str | None = None
    headless: bool = True
    browser_executable: str | None = None
    propagate_trace: bool = False

    @classmethod
    def from_env(cls):
        root = Path(__file__).resolve().parents[2]
        return cls(
            root=root,
            runner_script=Path(os.environ["MENDER_RUNNER_SCRIPT"]).resolve()
            if os.getenv("MENDER_RUNNER_SCRIPT") else None,
            runner_python=os.getenv("MENDER_RUNNER_PYTHON") or default_runner_python(root),
            runner_timeout=float(os.getenv("MENDER_RUNNER_TIMEOUT", "45")),
            agent_timeout=float(os.getenv("MENDER_AGENT_TIMEOUT", "90")),
            write_hosts=tuple(h.strip() for h in os.getenv("MENDER_WRITE_HOSTS", "").split(",") if h.strip()),
            demo_workflow=os.getenv("MENDER_DEMO_WORKFLOW"),
            headless=os.getenv("MENDER_HEADLESS", "true").lower() != "false",
            browser_executable=os.getenv("MENDER_BROWSER_EXECUTABLE"),
            propagate_trace=os.getenv("MENDER_PROPAGATE_TRACE", "false").lower() == "true",
        )

    @property
    def backend(self):
        return self.root / "services/backend"

    @property
    def workflows_dir(self):
        """The only place workflow definitions live, so the backend and the runner always agree."""
        return self.root / "contracts/workflows"

    def selectors_for(self, workflow_id: str):
        return self.root / "contracts/selectors" / f"{workflow_id}.json"

    @property
    def script(self):
        return self.runner_script or self.root / "services/runner/execute.py"


def load_workflow(path: Path):
    workflow = Workflow.model_validate(read_json(path))
    params_validator = validator(workflow.params_schema)
    output_validator = validator(workflow.output_schema)
    params_validator.validate(workflow.canary.params)
    output_validator.validate(workflow.canary.expected_output)
    masked_output(workflow.canary.expected_output, workflow.canary.ignore_paths)
    return workflow, params_validator, output_validator


def load_workflows(settings: Settings):
    return {path.stem: load_workflow(path) for path in sorted(settings.workflows_dir.glob("*.json"))}


def referenced_fields(definition):
    return {step.field for step in definition.steps} | {output.field for output in definition.outputs.values()}


def prune_runs(folder: Path, keep: int = 50):
    """Delete the oldest failure-artifact folders, keeping the newest `keep`. Run once at startup, never mid-run."""
    if not folder.is_dir():
        return 0
    runs = sorted((path for path in folder.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in runs[keep:]:
        shutil.rmtree(old, ignore_errors=True)
    return max(0, len(runs) - keep)


def masked_output(data: dict, paths: list[str]):
    """Ignore explicit JSON Pointer object fields, after raw schema validation."""
    result = json.loads(json.dumps(data, allow_nan=False))
    for pointer in paths:
        if not pointer.startswith("/") or pointer == "/":
            raise ValueError("Canary exclusions must name object fields using JSON Pointer")
        parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
        parent = result
        for part in parts[:-1]:
            if not isinstance(parent, dict) or part not in parent:
                raise ValueError(f"Missing canary exclusion path: {pointer}")
            parent = parent[part]
        if not isinstance(parent, dict) or parts[-1] not in parent:
            raise ValueError(f"Missing canary exclusion path: {pointer}")
        del parent[parts[-1]]
    def meaningful(value):
        if isinstance(value, dict):
            return any(meaningful(v) for v in value.values())
        if isinstance(value, list):
            return any(meaningful(v) for v in value)
        return True
    if paths and not meaningful(result):
        raise ValueError("Canary exclusions remove all meaningful comparison")
    return result
