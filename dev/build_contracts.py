#!/usr/bin/env python3
"""Regenerate everything under ``contracts/generated/`` from the hand-written sources.

One command, two steps, in order:

1. ``dev/build_schema.py``   -> ``contracts/generated/config.schema.json``
2. ``dev/build_contract.py`` -> ``contracts/generated/openapi.json``
   (``contracts/openapi.yaml`` with step 1's ``$defs`` merged over its
   ``x-tit-config`` placeholders)

The TypeScript third step lives in ``desktop/package.json`` because it needs
``node_modules``; ``npm run gen`` in ``desktop/`` runs this script and then
``openapi-typescript``.  Use ``npm run gen`` unless you have no Node.

Usage::

    python3 dev/build_contracts.py [--check]

Must run somewhere every registered config class is importable -- inside
``simnibs_python`` in the toolbox container, or on the host under ``pytest``
(``tests/conftest.py`` mocks SimNIBS/``bpy``/``trimesh``).  See
``contracts/README.md``.

``--check`` regenerates in memory and exits 1 if either output would change,
without writing.  ``dev/contracts_check.py`` calls the same code.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import build_contract  # noqa: E402  (dev/ is this file's own directory)
import build_schema  # noqa: E402


def _ensure_importable() -> None:
    """Make ``tit.config_io`` importable, mocking the heavy libs if they are absent.

    ``dev/build_schema.py`` imports every registered config class, whose packages
    reach SimNIBS, ``bpy`` and ``trimesh``.  Inside the container those are real.
    On a developer's host they are not, so we install exactly the mocks the test
    suite uses -- ``tests/conftest.py``'s ``pytest_configure`` is the single
    source of truth for that list, so this cannot drift from it.
    """
    try:
        import tit.config_io  # noqa: F401
        return
    except ImportError:
        pass

    spec = importlib.util.spec_from_file_location(
        "_tit_conftest", REPO_ROOT / "tests" / "conftest.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise
    conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conftest)
    conftest.pytest_configure(None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if either generated file would change; write nothing",
    )
    args = parser.parse_args(argv)

    _ensure_importable()

    rc = build_schema.main(["--check"] if args.check else [])
    if rc != 0:
        return rc
    return build_contract.main(["--check"] if args.check else [])


if __name__ == "__main__":
    raise SystemExit(main())
