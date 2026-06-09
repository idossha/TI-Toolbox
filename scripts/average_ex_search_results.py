#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Average TI-Toolbox ex-search ``final_output.csv`` files across subjects.

The script can either read explicit ``LABEL=/path/to/final_output.csv`` inputs,
or auto-discover result CSVs from one project using ``--project --subjects
--roi``.  It writes an averaged CSV, source manifest, summary text file, and
optional PNG visualizations into the chosen output directory.

Examples
--------
Average a ROI across one project::

    python3 scripts/average_ex_search_results.py \
      --project /path/to/CAPTI_montages \
      --subjects 001 002 003 \
      --roi thalamus_anterior_left \
      --analysis-name left_anterior_thalamus \
      --output-dir /path/to/CAPTI_montages/Montage_Analysis/AnteriorThalamus

Combine explicit Test-project inputs with auto-discovered CAPTI inputs::

    python3 scripts/average_ex_search_results.py \
      --input 999=/path/to/Test/.../sub-999/.../final_output.csv \
      --input LA=/path/to/Test/.../sub-LA/.../final_output.csv \
      --project /path/to/CAPTI_montages \
      --subjects 001 002 \
      --roi thalamus_anterior_left \
      --analysis-name left_anterior_thalamus \
      --output-dir /path/to/CAPTI_montages/Montage_Analysis/AnteriorThalamus
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


METRIC_COLUMNS = (
    "TImax_ROI",
    "TImean_ROI",
    "TImean_GM",
    "Focality",
    "Composite_Index",
)
CURRENT_COLUMNS = (
    "Current_Ch1_mA",
    "Current_Ch2_mA",
)
FINAL_OUTPUT_COLUMNS = (
    "Montage",
    *CURRENT_COLUMNS,
    *METRIC_COLUMNS,
)
NUMERIC_COLUMNS = (
    *CURRENT_COLUMNS,
    *METRIC_COLUMNS,
)
MONTAGE_RE = re.compile(r"^(E\d+)_(E\d+) <> (E\d+)_(E\d+)_I1-")
DEFAULT_TOP_N = 150


@dataclass(frozen=True)
class SourceCSV:
    """One subject/source CSV used in the average."""

    label: str
    path: Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_input(value: str) -> SourceCSV:
    """Parse ``LABEL=/path/to/final_output.csv`` CLI values."""
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "--input values must use LABEL=/path/to/final_output.csv"
        )
    label, path = value.split("=", 1)
    label = label.strip().removeprefix("sub-")
    path = path.strip()
    if not label or not path:
        raise argparse.ArgumentTypeError(
            "--input values must use LABEL=/path/to/final_output.csv"
        )
    return SourceCSV(label=label, path=Path(path).expanduser())


def discover_project_sources(
    project: Path,
    subjects: list[str],
    roi: str,
    net: str,
) -> list[SourceCSV]:
    """Build source CSV paths from standard ex-search output locations."""
    sources: list[SourceCSV] = []
    for subject in subjects:
        sid = subject.strip().removeprefix("sub-")
        path = (
            project
            / "derivatives"
            / "SimNIBS"
            / f"sub-{sid}"
            / "ex-search"
            / f"{roi}_sub-{sid}_{net}"
            / "final_output.csv"
        )
        sources.append(SourceCSV(label=sid, path=path))
    return sources


def read_ex_search_csv(path: Path) -> dict[str, dict[str, float]]:
    """Read one ex-search final_output.csv keyed by montage name."""
    rows: dict[str, dict[str, float]] = {}
    if not path.is_file():
        raise FileNotFoundError(f"Missing input CSV: {path}")

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        missing_cols = [
            col for col in ("Montage", *NUMERIC_COLUMNS) if col not in reader.fieldnames
        ]
        if missing_cols:
            raise ValueError(f"{path} is missing required column(s): {missing_cols}")

        for row in reader:
            montage = row["Montage"]
            rows[montage] = {
                col: float(row[col]) if row.get(col) not in ("", None) else math.nan
                for col in NUMERIC_COLUMNS
            }
    return rows


def average_sources(
    sources: list[SourceCSV],
    *,
    allow_partial: bool = False,
) -> tuple[list[dict], dict[str, dict[str, dict[str, float]]], int, int]:
    """Average metrics across source CSVs.

    Returns averaged rows, raw data, common montage count, and union montage
    count.  By default only montages present in every source are averaged.
    """
    data = {source.label: read_ex_search_csv(source.path) for source in sources}
    montage_sets = [set(rows) for rows in data.values()]
    common_montages = set.intersection(*montage_sets)
    union_montages = set.union(*montage_sets)
    montage_names = union_montages if allow_partial else common_montages

    averaged: list[dict] = []
    for montage in sorted(montage_names):
        match = MONTAGE_RE.match(montage)
        if not match:
            continue
        e1_plus, e1_minus, e2_plus, e2_minus = match.groups()
        row = {
            "Montage": montage,
            "E1_plus": e1_plus,
            "E1_minus": e1_minus,
            "E2_plus": e2_plus,
            "E2_minus": e2_minus,
        }
        present_labels = [label for label, rows in data.items() if montage in rows]
        row["n_subjects"] = len(present_labels)

        for metric in NUMERIC_COLUMNS:
            values = [data[label][montage][metric] for label in present_labels]
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            row[f"{metric}_mean"] = mean
            row[f"{metric}_std"] = math.sqrt(variance)
            for label in data:
                row[f"{metric}_{label}"] = (
                    data[label][montage][metric] if label in present_labels else ""
                )
        averaged.append(row)

    averaged.sort(key=lambda row: row["Focality_mean"], reverse=True)
    for rank, row in enumerate(averaged, 1):
        row["Focality_rank"] = rank
    for rank, row in enumerate(
        sorted(averaged, key=lambda row: row["Composite_Index_mean"], reverse=True),
        1,
    ):
        row["Composite_rank"] = rank
    averaged.sort(key=lambda row: row["Focality_mean"], reverse=True)

    return averaged, data, len(common_montages), len(union_montages)


def write_rows_csv(path: Path, rows: list[dict], fieldnames: list[str] | tuple[str, ...]) -> None:
    if not rows:
        raise ValueError("No rows to write.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def mean_final_output_rows(averaged: list[dict]) -> list[dict]:
    """Return mean rows in the same column shape as ex-search final_output.csv."""
    return [
        {
            "Montage": row["Montage"],
            **{col: row[f"{col}_mean"] for col in NUMERIC_COLUMNS},
        }
        for row in averaged
    ]


def subject_final_output_rows(
    averaged: list[dict],
    data: dict[str, dict[str, dict[str, float]]],
    label: str,
) -> list[dict]:
    """Return one subject's rows in the mean-focality montage ordering."""
    rows: list[dict] = []
    subject_data = data[label]
    for mean_row in averaged:
        montage = mean_row["Montage"]
        source_row = subject_data.get(montage, {})
        rows.append(
            {
                "Montage": montage,
                **{col: source_row.get(col, "") for col in NUMERIC_COLUMNS},
            }
        )
    return rows


def is_finite_number(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def excel_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def safe_sheet_name(name: str, used: set[str]) -> str:
    safe = re.sub(r"[\[\]:*?/\\]", "_", name).strip() or "Sheet"
    safe = safe[:31]
    base = safe
    suffix = 2
    while safe.lower() in used:
        suffix_text = f"_{suffix}"
        safe = f"{base[:31 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    used.add(safe.lower())
    return safe


def worksheet_xml(
    rows: list[dict],
    columns: list[str] | tuple[str, ...],
    *,
    freeze_header: bool = True,
) -> str:
    max_row = len(rows) + 1
    max_col = len(columns)
    ref = f"A1:{excel_column_name(max_col)}{max_row}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        f'<dimension ref="{ref}"/>',
    ]
    if freeze_header:
        parts.append(
            '<sheetViews><sheetView tabSelected="0" workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
        )
    parts.append("<sheetData>")

    def cell_xml(row_number: int, col_number: int, value) -> str:
        ref = f"{excel_column_name(col_number)}{row_number}"
        if value in ("", None) or (isinstance(value, float) and math.isnan(value)):
            return f'<c r="{ref}"/>'
        if is_finite_number(value):
            return f'<c r="{ref}"><v>{value:.12g}</v></c>'
        return (
            f'<c r="{ref}" t="inlineStr"><is><t>'
            f'{escape(str(value))}'
            "</t></is></c>"
        )

    parts.append('<row r="1">')
    for col_number, column in enumerate(columns, 1):
        parts.append(cell_xml(1, col_number, column))
    parts.append("</row>")

    for row_number, row in enumerate(rows, 2):
        parts.append(f'<row r="{row_number}">')
        for col_number, column in enumerate(columns, 1):
            parts.append(cell_xml(row_number, col_number, row.get(column, "")))
        parts.append("</row>")

    parts.extend(
        [
            "</sheetData>",
            f'<autoFilter ref="{ref}"/>',
            "</worksheet>",
        ]
    )
    return "".join(parts)


def write_average_workbook(
    path: Path,
    *,
    sources: list[SourceCSV],
    averaged: list[dict],
    data: dict[str, dict[str, dict[str, float]]],
) -> None:
    """Write a dependency-free XLSX with mean and per-subject tabs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    used_sheet_names: set[str] = set()
    sheets: list[tuple[str, list[dict], tuple[str, ...] | list[str]]] = [
        (safe_sheet_name("Mean", used_sheet_names), mean_final_output_rows(averaged), FINAL_OUTPUT_COLUMNS)
    ]
    for source in sources:
        sheets.append(
            (
                safe_sheet_name(source.label, used_sheet_names),
                subject_final_output_rows(averaged, data, source.label),
                FINAL_OUTPUT_COLUMNS,
            )
        )
    sheets.append(
        (
            safe_sheet_name("Sources", used_sheet_names),
            [
                {
                    "subject": source.label,
                    "source_csv_path": str(source.path),
                    "n_rows": len(data[source.label]),
                }
                for source in sources
            ],
            ["subject", "source_csv_path", "n_rows"],
        )
    )

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for index in range(1, len(sheets) + 1):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    content_types.append("</Types>")

    workbook_sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _, _) in enumerate(sheets, 1)
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{workbook_sheets}</sheets>"
        "</workbook>"
    )
    workbook_rels = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for index in range(1, len(sheets) + 1):
        workbook_rels.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    workbook_rels.append(
        f'<Relationship Id="rId{len(sheets) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    workbook_rels.append("</Relationships>")

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", "".join(content_types))
        xlsx.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        xlsx.writestr("xl/workbook.xml", workbook_xml)
        xlsx.writestr("xl/_rels/workbook.xml.rels", "".join(workbook_rels))
        xlsx.writestr("xl/styles.xml", styles_xml)
        for index, (_, rows, columns) in enumerate(sheets, 1):
            xlsx.writestr(
                f"xl/worksheets/sheet{index}.xml",
                worksheet_xml(rows, columns),
            )


def write_sources_csv(path: Path, sources: list[SourceCSV], data: dict) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["subject", "source_csv_path", "n_rows"])
        writer.writeheader()
        for source in sources:
            writer.writerow(
                {
                    "subject": source.label,
                    "source_csv_path": str(source.path),
                    "n_rows": len(data[source.label]),
                }
            )


def write_summary(
    path: Path,
    *,
    analysis_name: str,
    sources: list[SourceCSV],
    averaged: list[dict],
    common_count: int,
    union_count: int,
    allow_partial: bool,
    outputs: list[Path],
) -> None:
    with path.open("w") as f:
        f.write(f"{analysis_name} ex-search average across {len(sources)} subjects\n")
        f.write("Source CSVs remain in their original project folders.\n")
        f.write(f"Common montages: {common_count}\n")
        f.write(f"Union montages: {union_count}\n")
        f.write(
            "Averaging mode: "
            + ("partial montage union" if allow_partial else "strict common montage set")
            + "\n"
        )
        f.write(
            "Average final_output CSV uses the original final_output columns with mean values.\n"
        )
        f.write(
            "Average workbook tabs list Mean plus each subject in the same mean-focality order.\n"
        )
        f.write("\nSources:\n")
        for source in sources:
            f.write(f"- {source.label}: {source.path}\n")
        f.write("\nTop 10 by mean focality:\n")
        for row in averaged[:10]:
            f.write(
                f"{row['Focality_rank']:>3}. {row['Montage']} | "
                f"Focality_mean={row['Focality_mean']:.4f} | "
                f"TImean_ROI_mean={row['TImean_ROI_mean']:.4f} | "
                f"Composite_mean={row['Composite_Index_mean']:.4f}\n"
            )
        f.write("\nOutputs:\n")
        for output in outputs:
            f.write(f"- {output.name}\n")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    return slug or "average_ex_search"


def try_load_fonts():
    """Return PIL font objects, falling back to defaults."""
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    try:
        font = ImageFont.truetype(next(p for p in candidates if Path(p).exists()), 18)
        small = ImageFont.truetype(next(p for p in candidates if Path(p).exists()), 13)
        bold = ImageFont.truetype(
            next(p for p in bold_candidates if Path(p).exists()), 20
        )
    except (OSError, StopIteration):
        font = small = bold = ImageFont.load_default()
    return font, small, bold


def color_ramp(t: float, a=(0, 59, 112), b=(242, 142, 43)) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def viridisish(t: float) -> tuple[int, int, int]:
    stops = [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)]
    t = max(0.0, min(1.0, t)) * (len(stops) - 1)
    idx = min(int(t), len(stops) - 2)
    frac = t - idx
    return color_ramp(frac, stops[idx], stops[idx + 1])


def load_template_positions(coord_path: Path) -> dict[str, tuple[float, float]]:
    positions = {}
    with coord_path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 3 or row[0].strip().lower() == "electrode_name":
                continue
            positions[row[0].strip()] = (float(row[1]), float(row[2]))
    return positions


def quadratic_points(
    start: tuple[float, float],
    end: tuple[float, float],
    side: int,
) -> list[tuple[float, float]]:
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    dist = (dx * dx + dy * dy) ** 0.5
    if dist == 0:
        return [start, end]
    control = (
        (x1 + x2) / 2 + side * (-dy / dist) * min(dist * 0.22, 55),
        (y1 + y2) / 2 + side * (dx / dist) * min(dist * 0.22, 55),
    )
    points = []
    for i in range(31):
        t = i / 30
        x = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * control[0] + t**2 * x2
        y = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * control[1] + t**2 * y2
        points.append((x, y))
    return points


def render_focality_map(
    path: Path,
    averaged: list[dict],
    *,
    title: str,
    top_n: int,
    template_png: Path,
    coord_csv: Path,
) -> None:
    from PIL import Image, ImageDraw

    font, small, bold = try_load_fonts()
    positions = load_template_positions(coord_csv)
    top_rows = [
        row
        for row in averaged
        if all(row[key] in positions for key in ("E1_plus", "E1_minus", "E2_plus", "E2_minus"))
    ][:top_n]
    if not top_rows:
        raise ValueError("No plottable montages found for focality map.")

    base = Image.open(template_png).convert("RGBA")
    width, height = base.size
    canvas = Image.new("RGBA", (width + 210, height + 95), "white")
    canvas.alpha_composite(base, (0, 48))

    overlay = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    values = [row["Focality_mean"] for row in top_rows]
    vmin, vmax = min(values), max(values)
    if vmin == vmax:
        vmax += 1e-9

    for rank, row in enumerate(reversed(top_rows), 1):
        t = (row["Focality_mean"] - vmin) / (vmax - vmin)
        rgba = (*color_ramp(t), round(45 + 155 * rank / len(top_rows)))
        line_width = max(1, round(1 + 4 * rank / len(top_rows)))
        for start_key, end_key, side in (
            ("E1_plus", "E1_minus", 1),
            ("E2_plus", "E2_minus", -1),
        ):
            points = [
                (x, y + 48)
                for x, y in quadratic_points(
                    positions[row[start_key]], positions[row[end_key]], side
                )
            ]
            draw.line(points, fill=rgba, width=line_width)

    canvas.alpha_composite(overlay)
    draw = ImageDraw.Draw(canvas)
    best = top_rows[0]
    for key in ("E1_plus", "E1_minus", "E2_plus", "E2_minus"):
        x, y = positions[best[key]]
        y += 48
        draw.ellipse((x - 15, y - 15, x + 15, y + 15), outline=(255, 234, 0), width=5)
        draw.text((x + 16, y - 18), best[key], fill=(0, 0, 0), font=small)

    draw.text((18, 12), title, fill=(25, 25, 25), font=bold)
    draw.text(
        (18, height + 57),
        "Color = mean focality; highlighted electrodes = best mean-focality montage",
        fill=(25, 25, 25),
        font=small,
    )

    bar_x, bar_y, bar_w, bar_h = width + 58, 95, 26, height - 150
    for i in range(bar_h):
        t = 1 - i / max(1, bar_h - 1)
        draw.line((bar_x, bar_y + i, bar_x + bar_w, bar_y + i), fill=color_ramp(t))
    draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), outline=(30, 30, 30))
    draw.text((bar_x + 38, bar_y - 8), f"{vmax:.3f}", fill=(25, 25, 25), font=small)
    draw.text(
        (bar_x + 38, bar_y + bar_h - 10), f"{vmin:.3f}", fill=(25, 25, 25), font=small
    )
    draw.text((bar_x - 8, bar_y + bar_h + 18), "Mean focality", fill=(25, 25, 25), font=small)

    canvas.convert("RGB").save(path, quality=95)


def render_scatter(path: Path, averaged: list[dict], *, title: str) -> None:
    from PIL import Image, ImageDraw

    font, small, bold = try_load_fonts()
    image = Image.new("RGB", (1050, 790), "white")
    draw = ImageDraw.Draw(image)
    plot = (92, 70, 840, 665)
    left, top, right, bottom = plot

    xs = [row["TImean_ROI_mean"] for row in averaged]
    ys = [row["Focality_mean"] for row in averaged]
    cs = [row["Composite_Index_mean"] for row in averaged]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    cmin, cmax = min(cs), max(cs)
    xpad = (xmax - xmin) * 0.06 or 0.01
    ypad = (ymax - ymin) * 0.06 or 0.01
    xmin, xmax = xmin - xpad, xmax + xpad
    ymin, ymax = ymin - ypad, ymax + ypad

    def sx(x):
        return left + (x - xmin) / (xmax - xmin) * (right - left)

    def sy(y):
        return bottom - (y - ymin) / (ymax - ymin) * (bottom - top)

    for i in range(6):
        tx = xmin + (xmax - xmin) * i / 5
        x = sx(tx)
        draw.line((x, top, x, bottom), fill=(230, 230, 230))
        draw.text((x - 24, bottom + 12), f"{tx:.3f}", fill=(80, 80, 80), font=small)
        ty = ymin + (ymax - ymin) * i / 5
        y = sy(ty)
        draw.line((left, y, right, y), fill=(230, 230, 230))
        draw.text((18, y - 8), f"{ty:.2f}", fill=(80, 80, 80), font=small)

    draw.rectangle(plot, outline=(35, 35, 35), width=2)
    for row in averaged:
        t = (row["Composite_Index_mean"] - cmin) / (cmax - cmin or 1)
        color = viridisish(t)
        x, y = sx(row["TImean_ROI_mean"]), sy(row["Focality_mean"])
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color, outline=(20, 20, 20))

    for row in sorted(averaged, key=lambda r: r["Composite_Index_mean"], reverse=True)[:5]:
        x, y = sx(row["TImean_ROI_mean"]), sy(row["Focality_mean"])
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), outline=(0, 0, 0), width=2)

    draw.text((240, 24), title, fill=(25, 25, 25), font=bold)
    draw.text((365, 725), "Mean TImean_ROI (V/m)", fill=(25, 25, 25), font=font)
    draw.text((12, 34), "Mean focality", fill=(25, 25, 25), font=font)

    bar_x, bar_y, bar_w, bar_h = 905, 110, 28, 480
    for i in range(bar_h):
        t = 1 - i / max(1, bar_h - 1)
        draw.line((bar_x, bar_y + i, bar_x + bar_w, bar_y + i), fill=viridisish(t))
    draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), outline=(30, 30, 30))
    draw.text((bar_x + 42, bar_y - 8), f"{cmax:.3f}", fill=(25, 25, 25), font=small)
    draw.text(
        (bar_x + 42, bar_y + bar_h - 10), f"{cmin:.3f}", fill=(25, 25, 25), font=small
    )
    draw.text((bar_x - 15, bar_y + bar_h + 20), "Mean composite index", fill=(25, 25, 25), font=small)

    image.save(path, quality=95)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        dest="inputs",
        action="append",
        type=parse_input,
        default=[],
        help="Explicit source CSV as LABEL=/path/to/final_output.csv. Can repeat.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Project root for auto-discovered subject result CSVs.",
    )
    parser.add_argument(
        "--subjects",
        nargs="+",
        default=[],
        help="Subject IDs for --project auto-discovery.",
    )
    parser.add_argument(
        "--roi",
        help="ROI stem for auto-discovery, e.g. thalamus_anterior_left.",
    )
    parser.add_argument(
        "--net",
        default="GSN-HydroCel-256",
        help="EEG net suffix used in ex-search folder names.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--analysis-name",
        help="Output filename stem. Defaults to ROI or average_ex_search.",
    )
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Average the union of montages, using available subjects per montage.",
    )
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument(
        "--template-png",
        type=Path,
        default=repo_root() / "resources" / "amv" / "GSN-256.png",
    )
    parser.add_argument(
        "--template-coords",
        type=Path,
        default=repo_root() / "resources" / "amv" / "GSN-256.csv",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    sources: list[SourceCSV] = list(args.inputs)
    if args.project or args.subjects or args.roi:
        if not (args.project and args.subjects and args.roi):
            raise SystemExit("--project auto-discovery requires --project, --subjects, and --roi.")
        sources.extend(
            discover_project_sources(
                args.project.expanduser(),
                args.subjects,
                args.roi,
                args.net,
            )
        )

    if len(sources) < 2:
        raise SystemExit("Provide at least two source CSVs via --input and/or --project.")

    labels = [source.label for source in sources]
    if len(set(labels)) != len(labels):
        raise SystemExit(f"Duplicate source labels are not allowed: {labels}")

    analysis_name = args.analysis_name or args.roi or "average_ex_search"
    slug = slugify(analysis_name)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    averaged, data, common_count, union_count = average_sources(
        sources,
        allow_partial=args.allow_partial,
    )

    average_csv = args.output_dir / f"{slug}_average_final_output.csv"
    average_xlsx = args.output_dir / f"{slug}_average_by_subject.xlsx"
    sources_csv = args.output_dir / f"{slug}_sources.csv"
    summary_txt = args.output_dir / f"{slug}_average_summary.txt"
    write_rows_csv(average_csv, mean_final_output_rows(averaged), FINAL_OUTPUT_COLUMNS)
    write_average_workbook(
        average_xlsx,
        sources=sources,
        averaged=averaged,
        data=data,
    )
    write_sources_csv(sources_csv, sources, data)

    outputs = [average_csv, average_xlsx, sources_csv]
    if not args.no_plots:
        focality_png = args.output_dir / f"average_montage_focality_map_{slug}.png"
        scatter_png = args.output_dir / f"average_intensity_vs_focality_scatter_{slug}.png"
        render_focality_map(
            focality_png,
            averaged,
            title=f"Average focality map: {analysis_name}",
            top_n=args.top_n,
            template_png=args.template_png,
            coord_csv=args.template_coords,
        )
        render_scatter(
            scatter_png,
            averaged,
            title=f"Average intensity vs focality: {analysis_name}",
        )
        outputs.extend([focality_png, scatter_png])

    write_summary(
        summary_txt,
        analysis_name=analysis_name,
        sources=sources,
        averaged=averaged,
        common_count=common_count,
        union_count=union_count,
        allow_partial=args.allow_partial,
        outputs=outputs,
    )
    outputs.append(summary_txt)

    print(f"Averaged {len(averaged)} montage rows from {len(sources)} source CSVs.")
    print(f"Common montages: {common_count}; union montages: {union_count}.")
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
