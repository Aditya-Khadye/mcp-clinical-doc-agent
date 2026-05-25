"""Core tool implementations shared by the MCP server, FastAPI app, and LangGraph nodes.

Each tool function returns Pydantic-validated objects (or plain dicts ready for JSON
serialization, for MCP). They are intentionally deterministic and dependency-light so the
demo runs without an Anthropic API key. If ``ANTHROPIC_API_KEY`` is set, the summarizer
will use Claude for richer output.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from .schema import (
    AdverseEvent,
    AdverseEventCluster,
    ClinicalEntity,
    DocumentRef,
    ProtocolSummary,
)

DATA_DIR = Path(os.getenv("CLINICAL_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


# --- Heuristic dictionaries ------------------------------------------------------------------

_PHASE_RE = re.compile(r"\bPhase\s+(I{1,3}|IV|1|2|3|4|2b|3b)\b", re.IGNORECASE)
_POPULATION_RE = re.compile(r"\b(?:n|N)\s*=\s*(\d{2,5})\b")
_INDICATION_RE = re.compile(r"^\s*\*?\*?Indication\*?\*?\s*[:\-]\s*(.+)$", re.MULTILINE)
_INTERVENTION_RE = re.compile(
    r"^\s*\*?\*?Intervention\*?\*?\s*[:\-]\s*(.+)$", re.MULTILINE
)
_PRIMARY_ENDPOINT_RE = re.compile(
    r"^\s*\*?\*?Primary Endpoint\*?\*?\s*[:\-]\s*(.+)$", re.MULTILINE
)

# Crude clinical lexicon for offline entity extraction. Real systems would use SciSpacy / MetaMap.
_DRUG_SUFFIXES = (
    "mab",
    "nib",
    "tinib",
    "vir",
    "pril",
    "sartan",
    "olol",
    "azole",
    "cycline",
    "flozin",
    "glutide",
    "parin",
    "statin",
)
_CONDITION_KEYWORDS = {
    "non-small cell lung cancer",
    "nsclc",
    "heart failure",
    "hfref",
    "type 2 diabetes",
    "rheumatoid arthritis",
    "major depressive disorder",
    "depression",
    "atopic dermatitis",
    "crohn's disease",
    "alzheimer's disease",
    "amyotrophic lateral sclerosis",
    "als",
    "urinary tract infection",
    "uti",
    "metastatic",
}

# Body-system clusters for adverse events
_AE_CLUSTERS: dict[str, set[str]] = {
    "gastrointestinal": {
        "nausea",
        "vomiting",
        "diarrhea",
        "constipation",
        "abdominal pain",
        "dyspepsia",
    },
    "cardiovascular": {
        "hypertension",
        "hypotension",
        "tachycardia",
        "qt prolongation",
        "arrhythmia",
        "edema",
    },
    "neurological": {
        "headache",
        "dizziness",
        "insomnia",
        "fatigue",
        "somnolence",
        "neuropathy",
        "seizure",
    },
    "dermatological": {"rash", "pruritus", "urticaria", "alopecia", "injection site reaction"},
    "hematological": {
        "anemia",
        "neutropenia",
        "thrombocytopenia",
        "leukopenia",
        "lymphopenia",
    },
    "hepatic": {"elevated alt", "elevated ast", "hepatotoxicity", "transaminitis"},
    "respiratory": {"cough", "dyspnea", "pneumonitis", "bronchospasm"},
    "infections": {"upper respiratory infection", "urinary tract infection", "pneumonia"},
    "metabolic": {"hyperglycemia", "hypoglycemia", "hyperkalemia", "hyponatremia"},
}

_SEVERITY_HINTS = {
    "mild": "mild",
    "grade 1": "mild",
    "grade 2": "moderate",
    "moderate": "moderate",
    "severe": "severe",
    "grade 3": "severe",
    "grade 4": "severe",
    "grade 5": "severe",
}


# --- Helpers ---------------------------------------------------------------------------------


def _read_document(document_id: str) -> tuple[Path, str]:
    path = DATA_DIR / f"{document_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"No document with id={document_id!r} in {DATA_DIR}")
    return path, path.read_text(encoding="utf-8")


def _doc_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return fallback


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


# --- Tools -----------------------------------------------------------------------------------


def list_documents(data_dir: str | None = None) -> list[dict]:
    """Tool: list_documents. Returns metadata for every protocol in ``data/``."""
    base = Path(data_dir) if data_dir else DATA_DIR
    docs: list[DocumentRef] = []
    for path in sorted(base.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        doc_id = path.stem
        docs.append(
            DocumentRef(
                id=doc_id,
                title=_doc_title(text, doc_id),
                path=str(path),
                indication=_first_match(_INDICATION_RE, text),
                phase=_first_match(_PHASE_RE, text),
            )
        )
    return [d.model_dump() for d in docs]


def extract_entities(
    document_id: str | None = None, text: str | None = None
) -> list[dict]:
    """Tool: extract_entities. Heuristic NER over a protocol (drugs, conditions, endpoints)."""
    if document_id is None and text is None:
        # Process every document
        out: list[ClinicalEntity] = []
        for doc in list_documents():
            out.extend(
                ClinicalEntity.model_validate(e)
                for e in extract_entities(document_id=doc["id"])
            )
        return [e.model_dump() for e in out]

    if text is None:
        _, text = _read_document(document_id)  # type: ignore[arg-type]
    assert document_id is not None
    lower = text.lower()
    entities: list[ClinicalEntity] = []

    # Drugs: capitalized tokens + known suffixes
    drug_candidates = set()
    for tok in re.findall(r"\b[A-Z][a-zA-Z0-9-]{4,}\b", text):
        low = tok.lower()
        if any(low.endswith(s) for s in _DRUG_SUFFIXES):
            drug_candidates.add(tok)
    for d in sorted(drug_candidates):
        entities.append(ClinicalEntity(name=d, category="drug", document_id=document_id))

    # Conditions
    seen_conditions: set[str] = set()
    for kw in _CONDITION_KEYWORDS:
        if kw in lower and kw not in seen_conditions:
            seen_conditions.add(kw)
            entities.append(
                ClinicalEntity(
                    name=kw.title(), category="condition", document_id=document_id
                )
            )

    # Phase
    phase = _first_match(_PHASE_RE, text)
    if phase:
        entities.append(
            ClinicalEntity(name=f"Phase {phase}", category="phase", document_id=document_id)
        )

    # Intervention
    intervention = _first_match(_INTERVENTION_RE, text)
    if intervention:
        entities.append(
            ClinicalEntity(
                name=intervention, category="intervention", document_id=document_id
            )
        )

    # Endpoint
    endpoint = _first_match(_PRIMARY_ENDPOINT_RE, text)
    if endpoint:
        entities.append(
            ClinicalEntity(name=endpoint, category="endpoint", document_id=document_id)
        )

    # Population
    pop = _first_match(_POPULATION_RE, text)
    if pop:
        entities.append(
            ClinicalEntity(name=f"N={pop}", category="population", document_id=document_id)
        )

    return [e.model_dump() for e in entities]


def _extract_adverse_events(text: str, document_id: str) -> list[AdverseEvent]:
    ae_section = _isolate_section(text, ("Adverse Events", "Safety", "Side Effects"))
    target = ae_section if ae_section else text
    lower_target = target.lower()
    events: list[AdverseEvent] = []
    for cluster, terms in _AE_CLUSTERS.items():
        for term in terms:
            if term in lower_target:
                # Severity heuristic: look at a +/- 80-char window
                idx = lower_target.find(term)
                window = lower_target[max(0, idx - 80) : idx + 80]
                severity = "unknown"
                for hint, sev in _SEVERITY_HINTS.items():
                    if hint in window:
                        severity = sev  # type: ignore[assignment]
                        break
                freq_match = re.search(r"(\d{1,2}(?:\.\d+)?\s*%)", window)
                events.append(
                    AdverseEvent(
                        name=term,
                        severity=severity,  # type: ignore[arg-type]
                        frequency=freq_match.group(1) if freq_match else None,
                        document_id=document_id,
                    )
                )
                # We attach cluster info via the outer cluster_adverse_events tool, not here.
                _ = cluster
    return events


def _isolate_section(text: str, headers: tuple[str, ...]) -> str | None:
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if any(h.lower() in line.lower() for h in headers) and line.startswith(("#", "**")):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("# ") or lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def cluster_adverse_events(document_ids: list[str] | None = None) -> list[dict]:
    """Tool: cluster_adverse_events. Buckets AE mentions by body-system across protocols."""
    if document_ids is None:
        document_ids = [d["id"] for d in list_documents()]

    all_events: list[AdverseEvent] = []
    for doc_id in document_ids:
        _, text = _read_document(doc_id)
        all_events.extend(_extract_adverse_events(text, doc_id))

    by_cluster: dict[str, list[AdverseEvent]] = defaultdict(list)
    for ev in all_events:
        cluster = _cluster_for(ev.name)
        by_cluster[cluster].append(ev)

    clusters = [
        AdverseEventCluster(cluster_label=label, events=evs)
        for label, evs in sorted(by_cluster.items(), key=lambda x: -len(x[1]))
    ]
    return [c.model_dump() for c in clusters]


def _cluster_for(ae_name: str) -> str:
    for cluster, terms in _AE_CLUSTERS.items():
        if ae_name in terms:
            return cluster
    return "other"


def summarize_protocol(document_id: str) -> dict:
    """Tool: summarize_protocol. Structured summary of one protocol."""
    _, text = _read_document(document_id)
    title = _doc_title(text, document_id)
    phase = _first_match(_PHASE_RE, text)
    indication = _first_match(_INDICATION_RE, text)
    intervention = _first_match(_INTERVENTION_RE, text)
    primary_endpoint = _first_match(_PRIMARY_ENDPOINT_RE, text)
    pop_str = _first_match(_POPULATION_RE, text)
    population_size = int(pop_str) if pop_str else None

    events = _extract_adverse_events(text, document_id)
    ae_count = len(events)

    summary_text = _build_summary_text(
        title=title,
        phase=phase,
        indication=indication,
        intervention=intervention,
        primary_endpoint=primary_endpoint,
        population_size=population_size,
        ae_count=ae_count,
        events=events,
        full_text=text,
    )

    return ProtocolSummary(
        document_id=document_id,
        title=title,
        phase=f"Phase {phase}" if phase else None,
        indication=indication,
        intervention=intervention,
        primary_endpoint=primary_endpoint,
        population_size=population_size,
        adverse_event_count=ae_count,
        summary_text=summary_text,
    ).model_dump()


def _build_summary_text(
    *,
    title: str,
    phase: str | None,
    indication: str | None,
    intervention: str | None,
    primary_endpoint: str | None,
    population_size: int | None,
    ae_count: int,
    events: list[AdverseEvent],
    full_text: str,
) -> str:
    """Return a short summary string. Uses Claude if ANTHROPIC_API_KEY is set, else a template."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=api_key)
            prompt = (
                "You are a clinical research assistant. In 3-4 sentences, summarize this "
                "FDA-style trial protocol. Focus on intervention, population, primary endpoint, "
                "and notable safety signals.\n\n"
                f"PROTOCOL:\n{full_text[:6000]}"
            )
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            return _template_summary(
                title, phase, indication, intervention, primary_endpoint,
                population_size, ae_count, events, error=str(exc),
            )
    return _template_summary(
        title, phase, indication, intervention, primary_endpoint,
        population_size, ae_count, events,
    )


def _template_summary(
    title: str,
    phase: str | None,
    indication: str | None,
    intervention: str | None,
    primary_endpoint: str | None,
    population_size: int | None,
    ae_count: int,
    events: list[AdverseEvent],
    error: str | None = None,
) -> str:
    top_ae = ", ".join(name for name, _ in Counter(e.name for e in events).most_common(3))
    parts = [
        f"{title}: a {'Phase ' + phase if phase else 'clinical'} study"
        + (f" in {indication}." if indication else "."),
    ]
    if intervention:
        parts.append(f"Intervention: {intervention}.")
    if population_size:
        parts.append(f"Planned enrollment: N={population_size}.")
    if primary_endpoint:
        parts.append(f"Primary endpoint: {primary_endpoint}.")
    parts.append(
        f"Safety profile mentions {ae_count} adverse-event signals"
        + (f"; most frequent: {top_ae}." if top_ae else ".")
    )
    if error:
        parts.append(f"(Heuristic fallback — Claude call failed: {error[:80]})")
    return " ".join(parts)
