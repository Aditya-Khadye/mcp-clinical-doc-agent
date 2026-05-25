"""LangGraph nodes — each calls one MCP tool, mutating the shared state."""

from __future__ import annotations

from typing import TypedDict

from .. import tools as t
from ..schema import (
    AdverseEventCluster,
    ClinicalEntity,
    DocumentRef,
    ProtocolSummary,
)


class AgentState(TypedDict, total=False):
    """State carried between nodes in the LangGraph workflow."""

    documents: list[DocumentRef]
    entities: list[ClinicalEntity]
    clusters: list[AdverseEventCluster]
    summaries: list[ProtocolSummary]
    errors: list[str]


def ingest_node(state: AgentState) -> AgentState:
    """Step 1: discover all available protocols."""
    raw = t.list_documents()
    docs = [DocumentRef.model_validate(d) for d in raw]
    return {**state, "documents": docs, "errors": state.get("errors", [])}


def extract_node(state: AgentState) -> AgentState:
    """Step 2: extract clinical entities from every protocol."""
    all_entities: list[ClinicalEntity] = []
    errors = list(state.get("errors", []))
    for doc in state.get("documents", []):
        try:
            raw = t.extract_entities(document_id=doc.id)
            all_entities.extend(ClinicalEntity.model_validate(e) for e in raw)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"extract:{doc.id}:{exc}")
    return {**state, "entities": all_entities, "errors": errors}


def cluster_node(state: AgentState) -> AgentState:
    """Step 3: cluster adverse events across all protocols."""
    doc_ids = [d.id for d in state.get("documents", [])]
    errors = list(state.get("errors", []))
    try:
        raw = t.cluster_adverse_events(document_ids=doc_ids)
        clusters = [AdverseEventCluster.model_validate(c) for c in raw]
    except Exception as exc:  # noqa: BLE001
        errors.append(f"cluster:{exc}")
        clusters = []
    return {**state, "clusters": clusters, "errors": errors}


def summarize_node(state: AgentState) -> AgentState:
    """Step 4: produce a structured summary for each protocol."""
    summaries: list[ProtocolSummary] = []
    errors = list(state.get("errors", []))
    for doc in state.get("documents", []):
        try:
            raw = t.summarize_protocol(doc.id)
            summaries.append(ProtocolSummary.model_validate(raw))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"summarize:{doc.id}:{exc}")
    return {**state, "summaries": summaries, "errors": errors}
