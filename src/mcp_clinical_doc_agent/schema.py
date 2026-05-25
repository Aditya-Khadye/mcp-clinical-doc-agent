"""Pydantic schemas for the clinical document agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EntityCategory = Literal["drug", "condition", "intervention", "endpoint", "population", "phase"]
Severity = Literal["mild", "moderate", "severe", "unknown"]


class DocumentRef(BaseModel):
    """Reference to a clinical protocol document."""

    id: str
    title: str
    path: str
    indication: str | None = None
    phase: str | None = None


class ClinicalEntity(BaseModel):
    """A named entity extracted from a protocol (drug, condition, endpoint, etc.)."""

    name: str
    category: EntityCategory
    document_id: str
    context: str | None = Field(
        default=None, description="Short snippet around the entity mention"
    )


class AdverseEvent(BaseModel):
    """A reported adverse event from a protocol's safety section."""

    name: str
    severity: Severity = "unknown"
    frequency: str | None = None
    document_id: str


class AdverseEventCluster(BaseModel):
    """A group of related adverse events sharing a body-system label."""

    cluster_label: str
    events: list[AdverseEvent]

    @property
    def total_count(self) -> int:
        return len(self.events)


class ProtocolSummary(BaseModel):
    """Structured summary of one protocol."""

    document_id: str
    title: str
    phase: str | None = None
    indication: str | None = None
    intervention: str | None = None
    primary_endpoint: str | None = None
    population_size: int | None = None
    adverse_event_count: int = 0
    summary_text: str


class EvalResult(BaseModel):
    """Outcome of the eval step on a workflow report."""

    passed: bool
    checks: dict[str, bool]
    notes: list[str] = Field(default_factory=list)


class WorkflowReport(BaseModel):
    """Final JSON report produced by the LangGraph workflow."""

    documents_processed: list[DocumentRef]
    entities: list[ClinicalEntity]
    adverse_event_clusters: list[AdverseEventCluster]
    summaries: list[ProtocolSummary]
    eval_result: EvalResult

    @property
    def total_adverse_events(self) -> int:
        return sum(c.total_count for c in self.adverse_event_clusters)
