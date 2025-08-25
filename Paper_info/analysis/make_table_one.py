#!/usr/bin/env python3
"""
Generate a publication-ready descriptive statistics table ("Table 1") from a CSV.

Features
- Auto-detects categorical vs. continuous variables (override with flags)
- Optional grouping (e.g., by sex) with p-values
- Robust stats (median [IQR]) or normal stats (mean (SD))
- Exports: CSV, LaTeX (booktabs, black & white), Markdown

Usage example
  python Paper_info/analysis/make_table_one.py \
    --input Paper_info/data/demographics.csv \
    --groupby sex \
    --categorical sex \
    --robust \
    --output-dir Paper_info/results/tables \
    --outfile-prefix demographic_summary

Dependencies
  pip install tableone pandas numpy
  (p-values may require scipy)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Sequence

import pandas as pd


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a publication-ready descriptive statistics table from a CSV",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to input CSV file",
    )
    parser.add_argument(
        "--groupby",
        type=str,
        default=None,
        help="Optional column to group by (e.g., 'sex')",
    )
    parser.add_argument(
        "--categorical",
        nargs="*",
        default=None,
        help="List of categorical variable names. If omitted, inferred from non-numeric dtypes.",
    )
    parser.add_argument(
        "--nonnormal",
        nargs="*",
        default=None,
        help="Continuous variables to treat as non-normal (median [IQR]). Ignored if --robust is set.",
    )
    parser.add_argument(
        "--robust",
        action="store_true",
        help="Treat all continuous variables as non-normal (median [IQR]).",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=None,
        help="Variables to exclude from the table (e.g., IDs).",
    )
    parser.add_argument(
        "--pval",
        action="store_true",
        help="Include p-values when a groupby is provided.",
    )
    parser.add_argument(
        "--include-missing",
        action="store_true",
        help="Include the 'Missing' column in outputs. By default it is removed.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory to write outputs to",
    )
    parser.add_argument(
        "--outfile-prefix",
        type=str,
        default="table1",
        help="Base name for output files (without timestamp or extension)",
    )
    parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="Do not add a timestamp to output filenames",
    )
    parser.add_argument(
        "--formats",
        nargs="*",
        default=["csv", "latex", "md"],
        choices=["csv", "latex", "md"],
        help="Output formats to produce",
    )
    parser.add_argument(
        "--caption",
        type=str,
        default=None,
        help="Optional caption for LaTeX output",
    )
    return parser.parse_args(argv)


def detect_id_columns(columns: List[str]) -> List[str]:
    candidate_ids: List[str] = []
    for col in columns:
        name = col.lower()
        if "id" == name or name.endswith("_id") or name.startswith("id_") or "id" in name:
            candidate_ids.append(col)
    return candidate_ids


def ensure_tableone() -> None:
    try:
        import tableone  # noqa: F401
    except Exception as exc:  # pragma: no cover
        msg = (
            "The 'tableone' package is required. Install it with:\n"
            "  pip install tableone pandas numpy\n\n"
            f"Import error: {exc}"
        )
        print(msg, file=sys.stderr)
        sys.exit(1)


def build_table_one(
    df: pd.DataFrame,
    groupby: Optional[str],
    categorical: Optional[List[str]],
    nonnormal: Optional[List[str]],
    robust: bool,
    exclude: Optional[List[str]],
    include_pvalues: bool,
    include_missing: bool,
) -> pd.DataFrame:
    from tableone import TableOne

    df_work = df.copy()

    all_columns: List[str] = list(df_work.columns)

    excluded: List[str] = []
    if exclude:
        excluded.extend([c for c in exclude if c in all_columns])

    # Auto-detect ID-like columns and exclude them unless explicitly kept
    for c in detect_id_columns(all_columns):
        if c not in excluded and c != groupby:
            excluded.append(c)

    candidate_columns = [c for c in all_columns if c not in excluded and c != groupby]

    # Infer categorical if not provided
    if categorical is None:
        inferred_cats = [c for c in candidate_columns if not pd.api.types.is_numeric_dtype(df_work[c])]
        categorical = inferred_cats
    else:
        categorical = [c for c in categorical if c in candidate_columns or c == groupby]

    # Ensure groupby in categorical if present and not numeric
    if groupby is not None and groupby not in categorical:
        if not pd.api.types.is_numeric_dtype(df_work[groupby]):
            categorical.append(groupby)

    # Continuous variables are the rest
    continuous = [c for c in candidate_columns if c not in set(categorical)]

    # Choose non-normal variables
    if robust:
        nonnormal = continuous.copy()
    else:
        nonnormal = [c for c in (nonnormal or []) if c in continuous]

    columns = categorical + continuous

    t1 = TableOne(
        df_work,
        columns=columns,
        categorical=categorical,
        groupby=groupby,
        nonnormal=nonnormal,
        pval=bool(groupby) and include_pvalues,
    )

    # Convert to DataFrame
    if hasattr(t1, "tableone"):
        table_df = t1.tableone.copy()
    elif hasattr(t1, "to_dataframe"):
        table_df = t1.to_dataframe()  # type: ignore[attr-defined]
    else:  # pragma: no cover - fallback via string parsing
        table_df = pd.read_fwf(pd.compat.StringIO(str(t1)))

    # Remove "Missing" column unless explicitly requested
    if not include_missing:
        if isinstance(table_df.columns, pd.MultiIndex):
            cols_to_keep = []
            for col in table_df.columns:
                labels = list(col) if isinstance(col, tuple) else [col]
                if any(str(lbl).strip().lower() == "missing" for lbl in labels):
                    continue
                cols_to_keep.append(col)
            if cols_to_keep:
                table_df = table_df.loc[:, cols_to_keep]
        else:
            keep_simple = [c for c in table_df.columns if str(c).strip().lower() != "missing"]
            table_df = table_df.loc[:, keep_simple]

    return table_df


def save_outputs(
    table_df: pd.DataFrame,
    output_dir: Path,
    outfile_prefix: str,
    add_timestamp: bool,
    formats: List[str],
    caption: Optional[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") if add_timestamp else None
    stem = f"{outfile_prefix}_{timestamp}" if timestamp else outfile_prefix

    if "csv" in formats:
        csv_path = output_dir / f"{stem}.csv"
        table_df.to_csv(csv_path, encoding="utf-8")
        print(f"[saved] {csv_path}")

    if "latex" in formats:
        latex_path = output_dir / f"{stem}.tex"
        latex_str = table_df.to_latex(
            index=True,
            escape=False,
            longtable=False,
            multicolumn=True,
            multicolumn_format="c",
            bold_rows=False,
            column_format=None,
            na_rep="",
            caption=caption,
            label=None,
            position=None,
            # booktabs provides a clean, black & white look
            buf=None,
        )

        # Pandas to_latex uses booktabs only if 'hrules' style; most modern versions include \toprule etc.
        # Ensure booktabs header is present; if not, lightly patch it.
        if "\\toprule" not in latex_str:
            # Minimal patch to add booktabs-like rules
            latex_str = latex_str.replace("\\hline\n", "\\toprule\n", 1)
            latex_str = latex_str.replace("\\hline\n", "\\midrule\n")
            latex_str = latex_str.rstrip() + "\n\\bottomrule\n"

        latex_path.write_text(latex_str, encoding="utf-8")
        print(f"[saved] {latex_path}")

    if "md" in formats:
        md_path = output_dir / f"{stem}.md"
        try:
            md_str = table_df.to_markdown(index=True)
        except Exception:
            # Fallback: simple CSV-style text
            md_str = table_df.to_csv()
        md_path.write_text(md_str, encoding="utf-8")
        print(f"[saved] {md_path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if not args.input.exists():
        print(f"Input file does not exist: {args.input}", file=sys.stderr)
        return 2

    ensure_tableone()

    df = pd.read_csv(args.input)

    # Normalize column names: strip whitespace
    df.columns = [c.strip() for c in df.columns]

    table_df = build_table_one(
        df=df,
        groupby=args.groupby,
        categorical=args.categorical,
        nonnormal=args.nonnormal,
        robust=args.robust,
        exclude=args.exclude,
        include_pvalues=args.pval,
        include_missing=args.include_missing,
    )

    add_timestamp = not args.no_timestamp
    save_outputs(
        table_df=table_df,
        output_dir=args.output_dir,
        outfile_prefix=args.outfile_prefix,
        add_timestamp=add_timestamp,
        formats=args.formats,
        caption=args.caption,
    )

    # Also print a plain-text view to stdout for quick inspection
    try:
        # to_string of DataFrame produces a readable plain text
        print("\n" + table_df.to_string())
    except Exception:
        print("\n" + str(table_df))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


