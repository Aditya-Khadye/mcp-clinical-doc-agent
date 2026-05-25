"""Convenience entry point: ``python scripts/run_workflow.py``.

Equivalent to ``uv run mcp-clinical-doc-workflow`` but easier to invoke from IDEs.
"""

from mcp_clinical_doc_agent.graph.workflow import main

if __name__ == "__main__":
    main()
