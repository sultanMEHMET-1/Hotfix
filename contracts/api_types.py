"""Shared API models for the Mender contracts.

These Pydantic v2 models mirror the JSON schemas in contracts, including the
workflow response returned by the backend. Import them; do not duplicate the
shapes in services.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
