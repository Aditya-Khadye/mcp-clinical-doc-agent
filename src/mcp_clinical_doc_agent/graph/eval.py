"""Eval node — checks the workflow report against simple quality rules."""

from __future__ import annotations

from ..schema import (
    AdverseEventCluster,
    ClinicalEntity,
    DocumentRef,
    EvalResult,
    ProtocolSummary,
)

MIN_DOCUMENTS = 5
MIN_ENTITIES_PER_DOC = 3
MIN_ADVERSE_EVENTS_TOTAL = 25
MIN_CLUSTERS_DISTINCT = 4
SUMMARY_MIN_CHARS = 80


def evaluate(
    *,
    documents: list[DocumentRef],
    entities: list[ClinicalEntity],
    clusters: list[AdverseEventCluster],
    summaries: list[ProtocolSummary],
) -> EvalResult:
    """Apply pass/fail rules to the workflow output."""
    checks: dict[str, bool] = {}
    notes: list[str] = []

    n_docs = len(documents)
    checks[f"documents>={MIN_DOCUMENTS}"] = n_docs >= MIN_DOCUMENTS
    notes.append(f"Processed {n_docs} documents.")

    entities_per_doc = {d.id: 0 for d in documents}
    for e in entities:
        entities_per_doc[e.document_id] = entities_per_doc.get(e.document_id, 0) + 1
    under = [doc_id for doc_id, n in entities_per_doc.items() if n < MIN_ENTITIES_PER_DOC]
    checks[f"each_doc_has_>={MIN_ENTITIES_PER_DOC}_entities"] = not under
    if under:
        notes.append(f"Under-entity docs: {under}")

    total_ae = sum(c.total_count for c in clusters)
    checks[f"adverse_events>={MIN_ADVERSE_EVENTS_TOTAL}"] = total_ae >= MIN_ADVERSE_EVENTS_TOTAL
    notes.append(f"Total adverse events across clusters: {total_ae}.")

    checks[f"distinct_clusters>={MIN_CLUSTERS_DISTINCT}"] = len(clusters) >= MIN_CLUSTERS_DISTINCT
    notes.append(f"Distinct AE body-system clusters: {len(clusters)}.")

    short_summaries = [s.document_id for s in summaries if len(s.summary_text) < SUMMARY_MIN_CHARS]
    checks[f"summary_text>=`{SUMMARY_MIN_CHARS}`_chars"] = not short_summaries
    if short_summaries:
        notes.append(f"Short summaries: {short_summaries}")

    checks["summary_mentions_AE"] = all(
        ("adverse" in s.summary_text.lower())
        or ("safety" in s.summary_text.lower())
        or (s.adverse_event_count > 0)
        for s in summaries
    )

    return EvalResult(
        passed=all(checks.values()),
        checks=checks,
        notes=notes,
    )
