"""Smoke tests for the MCP tool implementations."""

from __future__ import annotations

from mcp_clinical_doc_agent import tools


def test_list_documents_returns_ten():
    docs = tools.list_documents()
    assert len(docs) == 10
    assert all({"id", "title", "path"} <= d.keys() for d in docs)


def test_extract_entities_for_single_doc():
    doc = tools.list_documents()[0]
    entities = tools.extract_entities(document_id=doc["id"])
    assert len(entities) >= 3
    cats = {e["category"] for e in entities}
    # Every protocol should yield at least a drug or intervention reference
    assert cats & {"drug", "intervention", "condition", "endpoint", "phase"}


def test_extract_entities_all_when_id_omitted():
    entities = tools.extract_entities()
    assert len(entities) > 30


def test_cluster_adverse_events_returns_known_buckets():
    clusters = tools.cluster_adverse_events()
    labels = {c["cluster_label"] for c in clusters}
    # We expect at least these body-system buckets to appear given our synthetic corpus
    assert {"gastrointestinal", "neurological", "dermatological"} <= labels
    assert sum(len(c["events"]) for c in clusters) >= 25


def test_summarize_protocol_has_required_fields():
    doc = tools.list_documents()[0]
    summary = tools.summarize_protocol(doc["id"])
    assert summary["document_id"] == doc["id"]
    assert summary["title"]
    assert summary["adverse_event_count"] >= 0
    assert len(summary["summary_text"]) >= 80
