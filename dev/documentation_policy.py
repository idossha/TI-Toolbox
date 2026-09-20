#!/usr/bin/env python3
"""Reject temporary requirement stores; durable intent belongs in canonical docs.

Exit codes are 0 for a compliant repository, 1 for a policy violation, and 2 when
no repository can be inspected. The rule rejects the lexical path itself so an
empty directory, file, broken symlink, or renamed-format store cannot bypass it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Sequence

FORBIDDEN = Path("docs/requirements")


def policy_issues(root: Path) -> list[str]:
    """Return remediation messages for documentation-policy violations."""
    forbidden = root / FORBIDDEN
    if os.path.lexists(forbidden):
        return [
            "remove docs/requirements and record durable behavior in "
            "docs/dev/ARCHITECTURE.md, rationale in DECISIONS.md, verification "
            "in TESTING.md, and open work in ROADMAP.md"
        ]
    return []


def repository_root(value: str | os.PathLike[str]) -> Path:
    """Validate and return an inspectable TI-Toolbox repository root."""
    root = Path(value)
    try:
        if (
            not root.is_dir()
            or not (root / "AGENTS.md").is_file()
            or not (root / "docs").is_dir()
        ):
            raise ValueError
        list((root / "docs").iterdir())
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot inspect repository root: {root}") from error
    return root


def main(argv: Sequence[str] | None = None) -> int:
    """Run the documentation policy over one repository root."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1 or (args and args[0].startswith("-")):
        print(
            "usage: python3 dev/documentation_policy.py [REPOSITORY_ROOT]",
            file=sys.stderr,
        )
        return 2
    default_root = Path(__file__).resolve().parents[1]
    try:
        root = repository_root(args[0] if args else default_root)
        issues = policy_issues(root)
    except (OSError, ValueError) as error:
        print(f"documentation_policy: {error}", file=sys.stderr)
        return 2
    if issues:
        for issue in issues:
            print(f"documentation_policy: {issue}", file=sys.stderr)
        return 1
    print("documentation_policy: canonical documentation layout is clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
