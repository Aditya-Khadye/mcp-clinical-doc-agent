"""End-to-end test for the LangGraph workflow."""

from __future__ import annotations

from mcp_clinical_doc_agent.graph.workflow import run


def test_workflow_runs_and_passes_eval():
    report = run()
    assert len(report.documents_processed) == 10
    assert len(report.entities) > 30
    assert report.total_adverse_events >= 25
    assert report.eval_result.passed, report.eval_result.notes
    # Each protocol should have a summary
    assert len(report.summaries) == 10
