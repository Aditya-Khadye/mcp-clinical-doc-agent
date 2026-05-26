"""Quick analysis demo over the ETL CSVs produced by the workflow.

Run after ``mcp-clinical-doc-workflow``:

    uv run python scripts/analyze.py
    uv run python scripts/analyze.py --etl-dir reports/etl

Prints three small Pandas-style tables:
  1. Per-protocol entity counts by category
  2. Top adverse events overall
  3. AE burden per protocol (joined: documents + adverse_events)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze the workflow ETL outputs.")
    parser.add_argument(
        "--etl-dir",
        type=Path,
        default=Path("reports/etl"),
        help="Directory containing the ETL CSVs (default: reports/etl).",
    )
    args = parser.parse_args()

    etl_dir: Path = args.etl_dir
    if not etl_dir.exists():
        raise SystemExit(
            f"No ETL directory at {etl_dir}. Run `uv run mcp-clinical-doc-workflow` first."
        )

    docs = pd.read_csv(etl_dir / "documents.csv")
    entities = pd.read_csv(etl_dir / "entities.csv")
    aes = pd.read_csv(etl_dir / "adverse_events.csv")

    pd.set_option("display.width", 120)
    pd.set_option("display.max_colwidth", 60)

    print("=" * 80)
    print("1) Entity counts per protocol, by category")
    print("=" * 80)
    pivot = (
        entities.groupby(["document_id", "category"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    print(pivot.to_string())

    print("\n" + "=" * 80)
    print("2) Top 10 adverse events overall")
    print("=" * 80)
    top = (
        aes.groupby("name")
        .agg(mentions=("document_id", "size"), protocols=("document_id", "nunique"))
        .sort_values("mentions", ascending=False)
        .head(10)
    )
    print(top.to_string())

    print("\n" + "=" * 80)
    print("3) Adverse-event burden per protocol (join: documents + adverse_events)")
    print("=" * 80)
    burden = (
        aes.groupby("document_id")
        .size()
        .rename("ae_count")
        .reset_index()
        .merge(docs[["id", "phase", "indication"]], left_on="document_id", right_on="id")
        .drop(columns=["id"])
        .sort_values("ae_count", ascending=False)
    )
    print(burden.to_string(index=False))


if __name__ == "__main__":
    main()
