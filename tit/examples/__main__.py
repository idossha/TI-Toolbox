"""``python -m tit.examples --project DIR [--list] [--force] [DATASET/PART ...]``

A part id is ``dataset/part`` -- ``ernie/headmodel``, ``mni152/nifti`` (``ernie:headmodel`` is
accepted too). ``DATASET`` on its own means every part of that dataset.
"""

from __future__ import annotations

import argparse
import sys

from tit.examples import DEFAULT_PART, catalogue, dataset_by_id, fetch, parse_part_id, status


def _expand(token: str) -> list[tuple[str, str]]:
    """``ernie/headmodel`` -> one part; a bare ``ernie`` -> every part of that dataset."""
    if "/" in token or ":" in token:
        return [parse_part_id(token)]
    return [(token, p.id) for p in dataset_by_id(token).parts]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tit.examples",
        description="Download example data (raw MRIs or finished head models) into a project.",
    )
    parser.add_argument("--project", required=True, help="BIDS project root")
    parser.add_argument("--list", action="store_true", help="list the catalogue and what is installed")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument(
        "parts",
        nargs="*",
        metavar="DATASET/PART",
        help=f"e.g. ernie/headmodel mni152/nifti; a bare DATASET means all its parts. "
        f"default: {DEFAULT_PART}",
    )
    args = parser.parse_args(argv)

    if args.list:
        installed = {s["id"]: s["installed"] for s in status(args.project)}
        for dataset in catalogue():
            print(f"{dataset.id}  {dataset.title}")
            for part in dataset.parts:
                mark = "installed" if installed[part.full_id] else "-"
                print(
                    f"  {part.full_id:20} {part.bytes / 1e6:7.0f} MB  {mark:9}  {part.meaning}"
                )
        return 0

    try:
        for token in args.parts or [DEFAULT_PART]:
            for dataset_id, part_id in _expand(token):
                fetch(dataset_id, part_id, args.project, force=args.force)
    except (OSError, ValueError, KeyError) as exc:
        print(f"tit.examples: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
