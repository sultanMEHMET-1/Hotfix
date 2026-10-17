"""Shared API models for the Mender contracts.

These Pydantic v2 models mirror contracts/selectors.schema.json,
contracts/failure_payload.schema.json, and the WorkflowExecutionResponse
returned by the backend. Import them; do not duplicate the shapes in services.
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


class WorkflowExecutionResponse(_StrictModel):
    """Result returned after a workflow run, including an optional heal."""

    status: Literal["success", "healed", "failed"]
    execution_time_ms: float
    data: dict[str, object]
    healed: bool
    trace_id: str = Field(min_length=1)
    diff: SelectorDiff | None = None
