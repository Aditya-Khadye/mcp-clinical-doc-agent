"""Pandas-based ETL: turn a ``WorkflowReport`` into analysis-ready tables.

Produces five tidy CSVs that any downstream notebook or BI tool can consume:

- ``documents.csv``         — one row per protocol
- ``entities.csv``          — one row per extracted entity
- ``adverse_events.csv``    — one row per AE mention (with cluster + doc)
- ``cluster_summary.csv``   — one row per AE body-system cluster (with top events)
- ``summaries.csv``         — one row per structured protocol summary

The shapes are intentionally normalized so they join cleanly on ``document_id``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from .schema import WorkflowReport


def to_frames(report: WorkflowReport) -> dict[str, pd.DataFrame]:
    """Convert a WorkflowReport into a dict of analysis-ready DataFrames."""
    documents_df = pd.DataFrame(
        [d.model_dump() for d in report.documents_processed]
    )

    entities_df = pd.DataFrame(
        [e.model_dump() for e in report.entities]
    )

    ae_rows: list[dict] = []
    cluster_rows: list[dict] = []
    for cluster in report.adverse_event_clusters:
        for ev in cluster.events:
            ae_rows.append({**ev.model_dump(), "cluster_label": cluster.cluster_label})
        top_terms = Counter(e.name for e in cluster.events).most_common(3)
        cluster_rows.append(
            {
                "cluster_label": cluster.cluster_label,
                "event_count": cluster.total_count,
                "distinct_terms": len({e.name for e in cluster.events}),
                "top_events": "; ".join(f"{name}({n})" for name, n in top_terms),
            }
        )
    adverse_events_df = pd.DataFrame(ae_rows)
    cluster_summary_df = pd.DataFrame(cluster_rows).sort_values(
        "event_count", ascending=False, ignore_index=True
    )

    summaries_df = pd.DataFrame(
        [s.model_dump() for s in report.summaries]
    )

    return {
        "documents": documents_df,
        "entities": entities_df,
        "adverse_events": adverse_events_df,
        "cluster_summary": cluster_summary_df,
        "summaries": summaries_df,
    }


def write_csvs(report: WorkflowReport, out_dir: str | Path) -> list[Path]:
    """Materialize each frame as a CSV under ``out_dir``. Returns paths written."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, df in to_frames(report).items():
        p = out_path / f"{name}.csv"
        df.to_csv(p, index=False)
        paths.append(p)
    return paths
