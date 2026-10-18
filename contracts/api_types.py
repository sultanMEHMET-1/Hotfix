"""Shared API models for the Mender contracts.

These Pydantic v2 models mirror the JSON schemas in contracts, including the
workflow response returned by the backend. Import them; do not duplicate the
shapes in services.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectorMap(_StrictModel):
    """Deterministic element targeting for one workflow."""

    workflow_id: str = Field(min_length=1, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    target_url: str = Field(min_length=1)
    version: int = Field(ge=1)
    fields: dict[str, str] = Field(min_length=1)


class FailurePayload(_StrictModel):
    """Artifact emitted when deterministic execution times out or fails."""

    workflow_id: str = Field(min_length=1, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    timestamp: float
    failed_step: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    expected_selector: str = Field(min_length=1)
    page_url: str = Field(min_length=1)
    dom_snippet: str = Field(min_length=1)
    screenshot_path: str = Field(min_length=1)
    error_message: str = Field(min_length=1)


class SelectorDiff(_StrictModel):
    """Selector change applied by the healer for one semantic field."""

    old_selector: str = Field(min_length=1)
    new_selector: str = Field(min_length=1)


class RecoveryError(_StrictModel):
    """Stable failure code and a human-readable explanation."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class HealEvidence(_StrictModel):
    """Executed action and element evidence grounding a field replacement."""

    action_type: str = Field(min_length=1)
    history_step: int = Field(ge=0)
    action_index: int = Field(ge=0)
    node_name: str = Field(min_length=1)
    attributes: dict[str, str]
    reasoning: str = Field(min_length=1)
    accessible_name: str | None = None
    xpath: str | None = None


class HealRecord(_StrictModel):
    """One candidate's final disposition after the recovery transaction ends."""

    field: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    diff: SelectorDiff
    evidence: HealEvidence
    verification_outcome: Literal["committed", "rolled_back", "rejected"]
    version_before: int = Field(ge=1)
    version_after: int | None = Field(default=None, ge=1)
    rollback_version: int | None = Field(default=None, ge=1)


class WorkflowExecutionResponse(_StrictModel):
    """Result returned after a workflow run, including an optional heal."""

    status: Literal["success", "healed", "failed"]
    execution_time_ms: float = Field(ge=0, allow_inf_nan=False)
    data: dict[str, object]
    healed: bool
    trace_id: str = Field(min_length=1)
    diff: SelectorDiff | None = None
    recovery_attempted: bool = False
    error: RecoveryError | None = None
    heal_records: list[HealRecord] = Field(default_factory=list)
    agent_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    agent_duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cooldown_remaining_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)


FIELD_NAME = r"^[a-z][a-z0-9_]*$"


class WorkflowStep(_StrictModel):
    """One ordered action. Input steps fill the named parameter; click steps press the element."""

    field: str = Field(pattern=FIELD_NAME)
    action_type: Literal["input", "click"]
    role: str | None = None
    label: str | None = None
    param: str | None = Field(default=None, pattern=FIELD_NAME)


class WorkflowOutput(_StrictModel):
    """How one output value is read after the actions: the element's text, or one of its attributes."""

    field: str = Field(pattern=FIELD_NAME)
    read: str = Field(pattern=r"^(text|attr:[A-Za-z_][A-Za-z0-9_:.-]*)$")


class WorkflowCanary(_StrictModel):
    """A known input and its known output, used to reject a repair that returns the wrong thing."""

    params: dict[str, object]
    expected_output: dict[str, object]
    ignore_paths: list[str] = Field(default_factory=list)


class WorkflowDefinition(_StrictModel):
    """A workflow any runner can execute: ordered steps, then reads. Lives in contracts/workflows/<id>.json."""

    goal: str = Field(min_length=1)
    steps: list[WorkflowStep] = Field(min_length=1)
    outputs: dict[str, WorkflowOutput] = Field(default_factory=dict)
    params_schema: dict[str, object]
    output_schema: dict[str, object]
    canary: WorkflowCanary
    # A workflow that changes data on the site. Runs only against local or allowlisted hosts.
    mutates: bool = False

    @model_validator(mode="after")
    def _consistent(self):
        step_fields = [step.field for step in self.steps]
        if len(set(step_fields)) != len(step_fields):
            raise ValueError("Duplicate ordered workflow fields")
        for step in self.steps:
            if step.action_type == "input" and not step.param:
                if self.outputs:  # a generic runner needs to know what to type
                    raise ValueError(f"Input step {step.field} needs a param")
        read_fields = {output.field for output in self.outputs.values()}
        if read_fields & set(step_fields):
            raise ValueError("A field cannot be both a step and an output")
        if self.outputs:
            properties = self.output_schema.get("properties", {})
            if set(self.outputs) != set(properties):
                raise ValueError("Outputs must cover exactly the output schema's properties")
            if any(not isinstance(p, dict) or p.get("type") != "string" for p in properties.values()):
                raise ValueError("Output values must be flat strings")
        return self


class WorkflowSummary(_StrictModel):
    """One entry of GET /api/v1/workflows, enough for a UI to offer and run the workflow."""

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    goal: str
    mutates: bool
    default: bool
    params_schema: dict[str, object]
    example_params: dict[str, object]
