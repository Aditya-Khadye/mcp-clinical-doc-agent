# mcp-clinical-doc-agent

> **MCP server + LangGraph agent for clinical trial protocol analysis.**
> Exposes four MCP tools (`list_documents`, `extract_entities`, `cluster_adverse_events`, `summarize_protocol`) consumable directly by Claude Code or Claude Desktop, and drives them through a LangGraph state machine (ingest → extract → cluster → summarize) that emits a Pydantic-validated JSON report with a built-in eval step. FastAPI HTTP surface and a slim Docker image for AWS deployment.

<sub>**Resume bullet (placeholder — replace with your own):** Designed and shipped an MCP server + LangGraph agent that ingests FDA-style clinical trial protocols, performs entity extraction, clusters adverse events by body system, and produces validated JSON summaries; integrated with Claude Code as a native tool provider and containerized for AWS deployment.</sub>

---

## What this project demonstrates

- **Model Context Protocol (MCP) server** built on the official Anthropic `mcp` Python SDK — 4 tools, stdio transport, registerable as a native tool provider in Claude Code and Claude Desktop.
- **LangGraph state machine** that orchestrates the same tools as a deterministic 4-node pipeline with typed state, error capture, and a final eval gate.
- **Pydantic v2 schemas** for every cross-boundary object (`DocumentRef`, `ClinicalEntity`, `AdverseEvent`, `AdverseEventCluster`, `ProtocolSummary`, `WorkflowReport`, `EvalResult`).
- **FastAPI HTTP surface** mirroring the MCP tools so the same business logic runs over HTTP for non-MCP clients.
- **Container-ready** for AWS — multi-stage Dockerfile, healthcheck, docker-compose for local parity.
- **Offline-first** — works with zero external API calls. Set `ANTHROPIC_API_KEY` to upgrade the summarizer to Claude Haiku 4.5.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  data/*.md   ── 10 synthetic FDA-style clinical trial protocols      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  src/mcp_clinical_doc_agent/tools.py                                 │
│  list_documents · extract_entities · cluster_adverse_events ·        │
│  summarize_protocol  (shared business logic)                         │
└──────────────────────────────────────────────────────────────────────┘
       │                       │                       │
       ▼                       ▼                       ▼
┌─────────────┐         ┌─────────────┐         ┌───────────────────┐
│ MCP server  │         │  FastAPI    │         │  LangGraph        │
│ (stdio)     │         │  HTTP       │         │  workflow         │
│ Claude Code │         │  /docs, /…  │         │  → JSON report    │
│ Claude Desk │         │  Docker     │         │  → eval gate      │
└─────────────┘         └─────────────┘         └───────────────────┘
```

---

## Quick start

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
# 1. Clone and install
git clone https://github.com/<you>/mcp-clinical-doc-agent
cd mcp-clinical-doc-agent
uv sync --extra dev

# 2. Run the LangGraph workflow end-to-end (writes reports/run.json)
uv run mcp-clinical-doc-workflow

# 3. Start the MCP server (stdio) for local testing
uv run mcp-clinical-doc-server

# 4. Or start the FastAPI HTTP surface
uv run mcp-clinical-doc-agent   # http://localhost:8000/docs

# 5. Tests
uv run pytest -v
```

---

## How to use this with Claude Code

This repo ships a project-scoped [`.mcp.json`](.mcp.json) at the root:

```json
{
  "mcpServers": {
    "clinical-doc-agent": {
      "command": "uv",
      "args": ["--directory", ".", "run", "mcp-clinical-doc-server"]
    }
  }
}
```

**To register:**

1. Open this directory in Claude Code: `cd mcp-clinical-doc-agent && claude`.
2. Run `/mcp` inside Claude Code — you should see `clinical-doc-agent` as a connected server with 4 tools.
3. Try prompts like:
   - *"List the clinical trial protocols you can see."*
   - *"Cluster the adverse events across all protocols and tell me which body system has the most reported events."*
   - *"Summarize the NSCLC protocol and flag any immune-related adverse events."*

Claude Code will call the MCP tools directly — you'll see tool-use blocks render inline.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and merge the contents of [`claude_desktop_config.example.json`](claude_desktop_config.example.json), replacing `/ABSOLUTE/PATH/TO/...` with your local checkout path. Restart Claude Desktop and the server will appear in the tool tray.

---

## The four MCP tools

| Tool | Input | Output |
|---|---|---|
| `list_documents` | — | `[{id, title, path, indication, phase}, …]` for every protocol in `data/`. |
| `extract_entities` | `document_id?` (omit to scan all) | List of `ClinicalEntity` — drugs, conditions, interventions, endpoints, populations, phase. |
| `cluster_adverse_events` | `document_ids?` (omit to scan all) | List of `AdverseEventCluster` bucketed by body system (gastrointestinal, cardiovascular, neurological, dermatological, hematological, hepatic, respiratory, infections, metabolic, other). |
| `summarize_protocol` | `document_id` | `ProtocolSummary` with phase, indication, intervention, primary endpoint, planned N, AE count, and a 3-4 sentence narrative. |

The summarizer uses Claude Haiku 4.5 when `ANTHROPIC_API_KEY` is set; otherwise it falls back to a deterministic template so the demo runs offline.

---

## The LangGraph workflow

A 4-node `StateGraph` over `AgentState`:

```
START → ingest → extract → cluster → summarize → END
                                                  ↓
                                          evaluate(report)
```

Each node calls one MCP tool and updates the shared state. `evaluate()` runs after the graph and applies six pass/fail checks on the assembled report:

- `documents >= 5`
- `each_doc_has_>=3_entities`
- `adverse_events >= 25`
- `distinct_clusters >= 4`
- `summary_text >= 80 chars`
- `summary_mentions_AE`

Output is a Pydantic-validated `WorkflowReport` written to `reports/run.json`. The CLI exits non-zero on eval failure.

```bash
uv run mcp-clinical-doc-workflow --output reports/run.json --print
```

Example tail of a run:

```
[workflow] eval: PASS
  ✓ documents>=5
  ✓ each_doc_has_>=3_entities
  ✓ adverse_events>=25
  ✓ distinct_clusters>=4
  ✓ summary_text>=`80`_chars
  ✓ summary_mentions_AE
  · Processed 10 documents.
  · Total adverse events across clusters: 79.
  · Distinct AE body-system clusters: 9.
```

---

## Docker / AWS deployment

Build and run locally with docker-compose:

```bash
docker-compose up --build
curl http://localhost:8000/health
curl http://localhost:8000/documents | jq .
curl -X POST http://localhost:8000/adverse-events/clusters \
     -H 'content-type: application/json' -d '{}' | jq '.[].cluster_label'
```

The Dockerfile is a multi-stage build (`python:3.11-slim-bookworm` + `uv`) with a built-in healthcheck. To push to ECR:

```bash
aws ecr create-repository --repository-name mcp-clinical-doc-agent
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <acct>.dkr.ecr.us-east-1.amazonaws.com
docker build -t mcp-clinical-doc-agent .
docker tag mcp-clinical-doc-agent:latest <acct>.dkr.ecr.us-east-1.amazonaws.com/mcp-clinical-doc-agent:latest
docker push <acct>.dkr.ecr.us-east-1.amazonaws.com/mcp-clinical-doc-agent:latest
```

From there, deploy to ECS Fargate, App Runner, or EKS. The container exposes port `8000`, serves a `/health` endpoint, and reads `ANTHROPIC_API_KEY` from env.

---

## Project layout

```
mcp-clinical-doc-agent/
├── .mcp.json                          # Claude Code project config
├── claude_desktop_config.example.json # Claude Desktop snippet
├── Dockerfile                         # Multi-stage build for AWS
├── docker-compose.yml
├── pyproject.toml                     # uv-managed
├── data/
│   └── protocol_*.md                  # 10 synthetic FDA-style protocols
├── src/mcp_clinical_doc_agent/
│   ├── tools.py                       # 4 tool implementations
│   ├── schema.py                      # Pydantic v2 models
│   ├── server.py                      # MCP server (stdio)
│   ├── api.py                         # FastAPI HTTP surface
│   └── graph/
│       ├── workflow.py                # LangGraph state machine
│       ├── nodes.py                   # ingest / extract / cluster / summarize
│       └── eval.py                    # Pass/fail report gate
├── tests/                             # pytest — tools + e2e workflow
├── scripts/run_workflow.py
└── reports/                           # JSON output (gitignored)
```

---

## Data

The `data/` directory contains 10 synthetic clinical trial protocols (~1-2 pages each in markdown) covering oncology (NSCLC, pembrolizumab), cardiology (HFrEF, SGLT2 inhibitor), endocrinology (T2D, dual GIP/GLP-1), rheumatology (RA, JAK1 inhibitor), psychiatry (treatment-resistant MDD, psilocybin analogue), dermatology (atopic dermatitis, IL-31R biologic), gastroenterology (Crohn's, anti-TL1A), neurology (early AD, anti-amyloid mAb), neurogenetics (SOD1 ALS, antisense oligonucleotide), and infectious disease (cUTI, novel cephalosporin).

Every protocol has the same canonical sections (Phase, Indication, Intervention, Primary Endpoint, N, Adverse Events) so the heuristic extractor can locate fields reliably.

---

## Demo

> _TODO: add a screen recording / GIF of Claude Code calling the MCP tools._
> Capture suggestion: open this repo in Claude Code, run `/mcp` to show the server connected, then ask "Cluster adverse events across all protocols and pick the top three by frequency." Record the inline tool-use blocks rendering with their inputs and outputs.

---

## License

MIT (or your preferred license — update this section).
