"""Entry point: ``simnibs_python -m tit.project_init spec.json``

The bug this file fixes
-----------------------
:data:`tit.jobs.kinds.MODULE_FOR_KIND` maps the ``project_init`` job kind to ``tit.project_init``
and :data:`tit.jobs.spec.CONTRACT_JOB_KINDS` lists it in the frozen wire contract, but the
package had no ``__main__``, so every submitted job died at exec::

    /root/SimNIBS-4.6/bin/simnibs_python: No module named tit.project_init.__main__;
    'tit.project_init' is a package and cannot be directly executed

(observed as job ``5d0c6180a8004f49`` in Dataset 000, 2026-08-27). ``kinds.module_exists()``
only checks that the *package* imports, which it always did -- so the kind looked wired up
right until it ran.

Shape
-----
The same thin JSON-config runner as :mod:`tit.opt.leadfield_runner` and
:mod:`tit.stats.nifti_average`: read the spec, initialise the
:class:`~tit.paths.PathManager` from ``project_dir``, do the work, exit 0/non-zero.
``project_init`` has no config dataclass (it is outside ``PipelineKind``, so
``/api/validate`` and ``/api/plan`` 404 for it by design); its config is the single boolean
``example_data``.

Idempotent by construction: :func:`tit.project_init.initialize_project_structure` creates only
what is missing, so re-running it on an established project is a no-op that still exits 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tit.paths import get_path_manager
from tit.project_init import initialize_project_structure, setup_example_data


def _toolbox_root() -> Path:
    """The checkout/install root that holds the bundled example data (``tit/``'s parent)."""
    return Path(__file__).resolve().parent.parent.parent


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("project_init: expected a config JSON path as the first argument", file=sys.stderr)
        return 2
    with open(args[0], encoding="utf-8") as fh:
        data = json.load(fh)

    project_dir = data.pop("project_dir", None)
    if not project_dir:
        print("project_init: config has no project_dir", file=sys.stderr)
        return 2
    get_path_manager(project_dir)

    from tit.jobs import events

    events.emit_stage("project_init")
    print(f"Project initialization: Started ({project_dir})", flush=True)

    initialize_project_structure(Path(project_dir))
    print(f"Project structure ready: {project_dir}", flush=True)

    if data.get("example_data"):
        copied = setup_example_data(_toolbox_root(), Path(project_dir))
        print(
            "Example data copied" if copied else "Example data already present; nothing copied",
            flush=True,
        )

    events.emit_result({"project_dir": str(project_dir)})
    print("✓ Project initialization complete.", flush=True)
    return 0


if __name__ == "__main__":
    code = main()
    try:
        from tit.jobs import events

        events.emit_exit(code)
    except Exception:  # pragma: no cover - never let bookkeeping change the exit code
        pass
    sys.exit(code)
