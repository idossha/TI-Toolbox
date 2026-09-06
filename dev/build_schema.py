#!/usr/bin/env python3
"""Regenerate ``contracts/schema.json`` from the ``tit`` config dataclasses.

Every class in ``tit.config_io.CONFIG_CLASS_REGISTRY`` contributes one
``$defs`` entry (its own name) plus whatever nested types its own
``tit.config_io.json_schema()`` call needs, merged into a single draft
2020-12 document. The document also carries an ``"x-tit-classes"`` index
(name -> Python import path) so a caller can go from a schema name straight
to the class that produced it.

Usage::

    python3 dev/build_schema.py [--check]

Must run somewhere the union of every registered class's own package can be
imported -- inside ``simnibs_python`` in the toolbox container (SimNIBS,
``bpy``, ``trimesh`` all present), or on the host under ``pytest`` (which
mocks those in ``tests/conftest.py``); a bare ``python3`` on the host cannot
import the blender classes (see ``tit/blender/__init__.py``).

Idempotent: re-running with no dataclass changes produces byte-identical
output, so CI can diff it (``--check`` exits 1 if the file would change
instead of writing it).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUTPUT_PATH = REPO_ROOT / "contracts" / "schema.json"


def build_schema() -> dict:
    """Assemble the combined ``contracts/schema.json`` document.

    Returns
    -------
    dict
        ``{"$schema": ..., "$defs": {<16 names + their nested types>},
        "x-tit-classes": {<16 names>: "<dotted.import.path>"}}``.

    Raises
    ------
    RuntimeError
        If two classes' nested ``$defs`` entries disagree under the same
        name -- this should be impossible after
        :func:`tit.config_io.json_schema`'s collision-safe renaming, so it
        would mean a new class was registered without updating
        ``tit.config_io._COLLIDING_DEFS_NAMES``.
    """
    from tit.config_io import CONFIG_CLASS_REGISTRY, json_schema, resolve_config_class

    combined_defs: dict[str, dict] = {}

    for name in sorted(CONFIG_CLASS_REGISTRY):
        cls = resolve_config_class(name)
        schema = json_schema(cls)
        nested_defs = schema.pop("$defs", {})

        combined_defs[name] = schema
        for def_name, def_schema in nested_defs.items():
            if def_name in combined_defs and combined_defs[def_name] != def_schema:
                raise RuntimeError(
                    f"$defs collision: {def_name!r} differs between {name!r} "
                    "and an earlier class. tit.config_io.json_schema() renames "
                    "every known colliding name -- add the new bare name to "
                    "tit.config_io._COLLIDING_DEFS_NAMES before regenerating."
                )
            combined_defs[def_name] = def_schema

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": combined_defs,
        "x-tit-classes": dict(sorted(CONFIG_CLASS_REGISTRY.items())),
    }


def render(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv

    doc = build_schema()
    rendered = render(doc)

    if check:
        current = OUTPUT_PATH.read_text() if OUTPUT_PATH.is_file() else None
        if current != rendered:
            print(
                f"{OUTPUT_PATH} is stale; run `python3 dev/build_schema.py` "
                "and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{OUTPUT_PATH} is up to date ({len(doc['$defs'])} $defs).")
        return 0

    OUTPUT_PATH.write_text(rendered)
    print(f"Wrote {OUTPUT_PATH} ({len(doc['$defs'])} $defs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
