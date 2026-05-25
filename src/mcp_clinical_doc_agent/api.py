"""FastAPI skeleton — exposes the same tools as the MCP server, over HTTP.

This is mostly here to satisfy the "FastAPI skeleton" requirement and to provide
a convenient way to exercise the toolset without an MCP host. It is intentionally
thin: no auth, no persistence, no rate limiting. Production deployments should
front it with an API gateway.
"""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import __version__, tools

app = FastAPI(
    title="Clinical Document Agent",
    description="HTTP surface for the clinical protocol analysis tools.",
    version=__version__,
)


class ClusterRequest(BaseModel):
    document_ids: list[str] | None = None


class ExtractRequest(BaseModel):
    document_id: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/documents")
def documents() -> list[dict]:
    return tools.list_documents()


@app.post("/entities")
def entities(req: ExtractRequest) -> list[dict]:
    try:
        return tools.extract_entities(document_id=req.document_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/adverse-events/clusters")
def clusters(req: ClusterRequest) -> list[dict]:
    try:
        return tools.cluster_adverse_events(document_ids=req.document_ids)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/documents/{document_id}/summary")
def summary(document_id: str) -> dict:
    try:
        return tools.summarize_protocol(document_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def main() -> None:
    """Entry point for ``mcp-clinical-doc-agent`` console script."""
    uvicorn.run(
        "mcp_clinical_doc_agent.api:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
