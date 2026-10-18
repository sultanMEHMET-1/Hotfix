"""Backend-owned workflow definitions and runtime configuration."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

import jsonschema
from pydantic import BaseModel, ConfigDict, Field


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


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    action_type: str = Field(min_length=1)
    role: str | None = None
    label: str | None = None


class Canary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    params: dict
    expected_output: dict
    ignore_paths: list[str] = Field(default_factory=list)


class Workflow(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    goal: str = Field(min_length=1)
    steps: list[Step] = Field(min_length=1)
    params_schema: dict
    output_schema: dict
    canary: Canary | None = None


@dataclass
class Settings:
    root: Path
    workflows_dir: Path | None = None
    runner_script: Path | None = None
    runner_python: str = sys.executable
    runner_timeout: float = 45
    agent_timeout: float = 90
    recovery_timeout: float = 240
    cleanup_reserve: float = 30
    lock_timeout: float = 5
    demo_workflow: str | None = None
    headless: bool = True
    browser_executable: str | None = None
    propagate_trace: bool = False

    @classmethod
    def from_env(cls):
        root = Path(__file__).resolve().parents[2]
        return cls(
            root=root,
            workflows_dir=Path(os.environ["MENDER_WORKFLOWS_DIR"]).resolve()
            if os.getenv("MENDER_WORKFLOWS_DIR") else None,
            runner_script=Path(os.environ["MENDER_RUNNER_SCRIPT"]).resolve()
            if os.getenv("MENDER_RUNNER_SCRIPT") else None,
            runner_python=os.getenv("MENDER_RUNNER_PYTHON", sys.executable),
            runner_timeout=float(os.getenv("MENDER_RUNNER_TIMEOUT", "45")),
            agent_timeout=float(os.getenv("MENDER_AGENT_TIMEOUT", "90")),
            demo_workflow=os.getenv("MENDER_DEMO_WORKFLOW"),
            headless=os.getenv("MENDER_HEADLESS", "true").lower() != "false",
            browser_executable=os.getenv("MENDER_BROWSER_EXECUTABLE"),
            propagate_trace=os.getenv("MENDER_PROPAGATE_TRACE", "false").lower() == "true",
        )

    @property
    def backend(self):
        return self.root / "services/backend"

    @property
    def selectors(self):
        return self.root / "contracts/selectors.json"

    @property
    def script(self):
        return self.runner_script or self.root / "services/runner/execute.py"


def load_workflows(settings: Settings):
    shared = settings.root / "contracts/workflows"
    folder = settings.workflows_dir or (shared if shared.is_dir() else settings.backend / "workflows")
    workflows = {}
    for path in sorted(folder.glob("*.json")):
        workflow = Workflow.model_validate(read_json(path))
        if len({step.field for step in workflow.steps}) != len(workflow.steps):
            raise ValueError(f"Duplicate ordered workflow fields in {path.name}")
        params_validator = validator(workflow.params_schema)
        output_validator = validator(workflow.output_schema)
        if workflow.canary:
            params_validator.validate(workflow.canary.params)
            output_validator.validate(workflow.canary.expected_output)
            masked_output(workflow.canary.expected_output, workflow.canary.ignore_paths)
        workflows[path.stem] = (workflow, params_validator, output_validator)
    return workflows


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
