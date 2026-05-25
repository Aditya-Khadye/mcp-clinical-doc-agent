"""MCP server exposing the clinical document tools over stdio.

Run directly: ``uv run mcp-clinical-doc-server`` or ``python -m mcp_clinical_doc_agent.server``.
Register with Claude Code via the .mcp.json at the project root.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import tools as t

mcp = FastMCP("clinical-doc-agent")


@mcp.tool()
def list_documents() -> list[dict]:
    """List all clinical trial protocol documents available in the data directory.

    Returns one entry per protocol with id, title, path, indication, and phase.
    Use this tool first to discover what documents are available, then pass an
    ``id`` from the result to ``extract_entities`` or ``summarize_protocol``.
    """
    return t.list_documents()


@mcp.tool()
def extract_entities(document_id: str | None = None) -> list[dict]:
    """Extract clinical entities (drugs, conditions, interventions, endpoints, populations).

    If ``document_id`` is omitted, runs across every document and returns the combined set.
    Each entity carries its source ``document_id`` so callers can group results.
    """
    return t.extract_entities(document_id=document_id)


@mcp.tool()
def cluster_adverse_events(document_ids: list[str] | None = None) -> list[dict]:
    """Identify and group adverse-event mentions across one or more protocols.

    Returns clusters bucketed by body system (gastrointestinal, cardiovascular,
    neurological, dermatological, hematological, hepatic, respiratory, infections,
    metabolic, other). If ``document_ids`` is omitted, clusters across all protocols.
    """
    return t.cluster_adverse_events(document_ids=document_ids)


@mcp.tool()
def summarize_protocol(document_id: str) -> dict:
    """Generate a structured summary of a single protocol.

    Returns phase, indication, intervention, primary endpoint, planned enrollment,
    adverse-event count, and a 3-4 sentence narrative. Uses Claude (Haiku) when
    ``ANTHROPIC_API_KEY`` is set; otherwise falls back to a deterministic template.
    """
    return t.summarize_protocol(document_id)


def main() -> None:
    """Entry point for ``mcp-clinical-doc-server`` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
