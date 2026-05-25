"""Verify the Pandas ETL step produces well-shaped, joinable frames."""

from __future__ import annotations

from pathlib import Path

from mcp_clinical_doc_agent import etl
from mcp_clinical_doc_agent.graph.workflow import run


def test_to_frames_shapes_and_joins():
    report = run()
    frames = etl.to_frames(report)

    # All five expected tables present
    assert set(frames) == {
        "documents",
        "entities",
        "adverse_events",
        "cluster_summary",
        "summaries",
    }

    docs = frames["documents"]
    entities = frames["entities"]
    aes = frames["adverse_events"]
    clusters = frames["cluster_summary"]
    summaries = frames["summaries"]

    assert len(docs) == 10
    assert {"id", "title", "phase", "indication"} <= set(docs.columns)
    assert {"document_id", "category", "name"} <= set(entities.columns)
    assert {"cluster_label", "document_id", "name"} <= set(aes.columns)
    assert {"cluster_label", "event_count", "top_events"} <= set(clusters.columns)
    assert {"document_id", "summary_text", "adverse_event_count"} <= set(summaries.columns)

    # Joinability: every entity's doc_id is in documents
    assert set(entities["document_id"]).issubset(set(docs["id"]))
    assert set(aes["document_id"]).issubset(set(docs["id"]))
    assert set(summaries["document_id"]).issubset(set(docs["id"]))

    # Cluster summary aggregates match the adverse_events frame
    by_cluster = aes.groupby("cluster_label").size().to_dict()
    for _, row in clusters.iterrows():
        assert row["event_count"] == by_cluster[row["cluster_label"]]


def test_write_csvs(tmp_path: Path):
    report = run()
    paths = etl.write_csvs(report, tmp_path)
    assert len(paths) == 5
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)
