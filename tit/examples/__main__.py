"""``python -m tit.examples --project DIR [--list] [--force] [SAMPLE_ID ...]``"""

from __future__ import annotations

import argparse
import sys

from tit.examples import ERNIE_HEADMODEL, catalogue, fetch, status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tit.examples",
        description="Download example datasets (raw MRIs or finished head models) into a project.",
    )
    parser.add_argument("--project", required=True, help="BIDS project root")
    parser.add_argument("--list", action="store_true", help="list the catalogue and what is installed")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("samples", nargs="*", metavar="SAMPLE_ID", help=f"default: {ERNIE_HEADMODEL}")
    args = parser.parse_args(argv)

    if args.list:
        installed = {s["id"]: s["installed"] for s in status(args.project)}
        for s in catalogue():
            mark = "installed" if installed[s.id] else "-"
            print(f"{s.id:18} {s.bytes / 1e6:7.0f} MB  {mark:9}  {s.title}")
        return 0

    try:
        for sample_id in args.samples or [ERNIE_HEADMODEL]:
            fetch(sample_id, args.project, force=args.force)
    except (OSError, ValueError, KeyError) as exc:
        print(f"tit.examples: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
