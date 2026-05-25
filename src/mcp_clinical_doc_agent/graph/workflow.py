"""LangGraph state machine: ingest -> extract -> cluster -> summarize -> eval.

Run end-to-end with: ``uv run mcp-clinical-doc-workflow [--output reports/run.json]``.
Returns a ``WorkflowReport`` (Pydantic) and writes it to disk as JSON.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from .. import etl
from ..schema import WorkflowReport
from .eval import evaluate
from .nodes import (
    AgentState,
    cluster_node,
    extract_node,
    ingest_node,
    summarize_node,
)


def build_graph():
    """Compile the LangGraph state machine."""
    g = StateGraph(AgentState)
    g.add_node("ingest", ingest_node)
    g.add_node("extract", extract_node)
    g.add_node("cluster", cluster_node)
    g.add_node("summarize", summarize_node)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "extract")
    g.add_edge("extract", "cluster")
    g.add_edge("cluster", "summarize")
    g.add_edge("summarize", END)
    return g.compile()


def run() -> WorkflowReport:
    """Execute the workflow and produce a validated report."""
    graph = build_graph()
    final_state: AgentState = graph.invoke({})  # type: ignore[assignment]

    documents = final_state.get("documents", [])
    entities = final_state.get("entities", [])
    clusters = final_state.get("clusters", [])
    summaries = final_state.get("summaries", [])

    eval_result = evaluate(
        documents=documents,
        entities=entities,
        clusters=clusters,
        summaries=summaries,
    )

    return WorkflowReport(
        documents_processed=documents,
        entities=entities,
        adverse_event_clusters=clusters,
        summaries=summaries,
        eval_result=eval_result,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the clinical-doc-agent LangGraph workflow.")
    parser.add_argument(
        "--output",
        type=str,
        default="reports/run.json",
        help="Where to write the JSON report (default: reports/run.json)",
    )
    parser.add_argument(
        "--etl-dir",
        type=str,
        default="reports/etl",
        help="Directory for Pandas-derived CSVs (default: reports/etl). Set to empty to skip.",
    )
    parser.add_argument(
        "--print", action="store_true", help="Also print the report to stdout."
    )
    args = parser.parse_args()

    report = run()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.model_dump_json(indent=2))

    csv_paths: list[Path] = []
    if args.etl_dir:
        csv_paths = etl.write_csvs(report, args.etl_dir)

    eval_result = report.eval_result
    status = "PASS" if eval_result.passed else "FAIL"
    print(f"[workflow] eval: {status}", file=sys.stderr)
    for check, ok in eval_result.checks.items():
        print(f"  {'✓' if ok else '✗'} {check}", file=sys.stderr)
    for note in eval_result.notes:
        print(f"  · {note}", file=sys.stderr)
    print(f"[workflow] report written to: {out_path}", file=sys.stderr)
    if csv_paths:
        print(
            f"[workflow] etl: {len(csv_paths)} CSVs → {csv_paths[0].parent}",
            file=sys.stderr,
        )

    if args.print:
        print(report.model_dump_json(indent=2))

    sys.exit(0 if eval_result.passed else 1)


if __name__ == "__main__":
    main()
