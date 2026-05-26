"""Helpers for reusable exhaustive-search electrode buckets."""

from __future__ import annotations

import csv
import json
from pathlib import Path


BUCKET_KEYS = ("e1_plus", "e1_minus", "e2_plus", "e2_minus")

BUCKET_ALIASES = {
    "e1_plus": "e1_plus",
    "e1+": "e1_plus",
    "e1plus": "e1_plus",
    "e1 plus": "e1_plus",
    "e1_minus": "e1_minus",
    "e1-": "e1_minus",
    "e1_": "e1_minus",
    "e1minus": "e1_minus",
    "e1 minus": "e1_minus",
    "e2_plus": "e2_plus",
    "e2+": "e2_plus",
    "e2plus": "e2_plus",
    "e2 plus": "e2_plus",
    "e2_minus": "e2_minus",
    "e2-": "e2_minus",
    "e2_": "e2_minus",
    "e2minus": "e2_minus",
    "e2 minus": "e2_minus",
}

QUADRANT_BUCKET_LABELS = {
    "e1_plus": "left anterior",
    "e1_minus": "right anterior",
    "e2_plus": "left posterior",
    "e2_minus": "right posterior",
}


def _normalize_bucket_key(key: str) -> str:
    normalized = key.strip().lower().replace("-", "_")
    normalized = " ".join(normalized.split())
    return BUCKET_ALIASES.get(normalized, normalized)


def _split_electrodes(value) -> list[str]:
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
    else:
        parts = list(value)
    return [str(e).strip() for e in parts if str(e).strip()]


def normalize_buckets(raw: dict) -> dict[str, list[str]]:
    """Normalize a bucket mapping to canonical ex-search bucket keys."""
    buckets = {key: [] for key in BUCKET_KEYS}
    for key, value in raw.items():
        bucket_key = _normalize_bucket_key(str(key))
        if bucket_key in buckets:
            buckets[bucket_key] = _split_electrodes(value)
    return buckets


def load_bucket_file(path: str | Path) -> dict[str, list[str]]:
    """Load bucket definitions from JSON, CSV, or TSV.

    JSON may use canonical keys (``e1_plus``) or GUI-style keys
    (``E1+``). CSV/TSV files should have one row per bucket, with the
    bucket name in the first column and electrodes in the remaining columns
    or as a comma/semicolon separated second column.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Bucket JSON must contain an object")
        return normalize_buckets(data)

    delimiter = "\t" if suffix == ".tsv" else ","
    rows = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if not row or not row[0].strip() or row[0].strip().startswith("#"):
                continue
            bucket_key = _normalize_bucket_key(row[0])
            if bucket_key not in BUCKET_KEYS:
                continue
            if len(row) == 2:
                rows[bucket_key] = _split_electrodes(row[1])
            else:
                rows[bucket_key] = _split_electrodes(row[1:])
    return normalize_buckets(rows)


def save_bucket_file(path: str | Path, buckets: dict[str, list[str]]) -> None:
    """Save bucket definitions as JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalize_buckets(buckets), f, indent=2)
        f.write("\n")


def build_quadrant_buckets(eeg_csv_path: str | Path) -> dict[str, list[str]]:
    """Split an EEG-position CSV into four RAS quadrants.

    Mapping:
    ``E1+`` = left anterior, ``E1-`` = right anterior,
    ``E2+`` = left posterior, ``E2-`` = right posterior.
    """
    buckets = {key: [] for key in BUCKET_KEYS}
    with open(eeg_csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 5 or row[0].strip().lower() != "electrode":
                continue
            try:
                x = float(row[1])
                y = float(row[2])
            except ValueError:
                continue
            label = row[4].strip()
            if not label:
                continue

            if x < 0 and y >= 0:
                buckets["e1_plus"].append(label)
            elif x >= 0 and y >= 0:
                buckets["e1_minus"].append(label)
            elif x < 0 and y < 0:
                buckets["e2_plus"].append(label)
            else:
                buckets["e2_minus"].append(label)

    return {key: sorted(values) for key, values in buckets.items()}
