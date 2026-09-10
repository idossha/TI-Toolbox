"""Created-path manifest for the smoke harness (decision P6).

What this pins
--------------
The harness deletes **exactly** the paths it created and nothing else. Every path a row will
write to is *claimed* before its job is submitted; the claim records whether the path already
existed on disk at that moment. ``remove_created()`` then deletes only the claims whose
``pre_existed`` is ``False``.

The failure it prevents
-----------------------
The dataset the whole program runs against is the maintainer's own (``/Users/idohaber/datasets/
000``: ``m2m_101``, ``m2m_ernie``, ``m2m_MNI152``, the ``docs_*`` runs the documentation is
built from). A cleanup that deletes "the row's output directory" unconditionally destroys a
pre-existing output the moment a row's namespacing is wrong, a recorded UI payload from lane S2
targets a real run name, or a test is re-run with ``--keep`` from a previous session. Recording
pre-existence at claim time turns that class of mistake into a skipped deletion plus a printed
line, instead of data loss.

Paths are *container* paths (``/mnt/000/...``) because that is what every API response carries
(``JobStatus.artifacts[].path``, ``PlanJob.output_dir``); :func:`host_path` maps them onto the
bind mount for the host-side ``stat``/``rmtree``.

Reproduce: ``dev/smoke.sh`` writes the manifest to ``tests/smoke/artifacts/manifest-<runid>.json``.

Deliberately elsewhere: what each row creates (:mod:`tests.smoke.matrix`).

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field


@dataclass
class Claim:
    """One path the harness may have to remove afterwards."""

    container_path: str
    host_path: str
    row_id: str
    pre_existed: bool
    #: set by :meth:`Manifest.remove_created`
    removed: bool = False
    note: str = ""


@dataclass
class Manifest:
    """Every path claimed during one harness run.

    Parameters
    ----------
    container_root, host_root : str
        The two names of the project directory (``/mnt/000`` and the host directory the dev
        container binds there). Every claim is translated between them once, at claim time.
    keep : bool
        ``--smoke-keep``: claims are still recorded (and written out) but nothing is deleted,
        so a failing row can be inspected on disk.
    """

    container_root: str
    host_root: str
    keep: bool = False
    claims: list[Claim] = field(default_factory=list)

    def host_path(self, container_path: str) -> str:
        """``/mnt/000/x`` -> ``<host_root>/x``; any other absolute path is returned unchanged."""
        root = self.container_root.rstrip("/")
        if container_path == root:
            return self.host_root
        if container_path.startswith(root + "/"):
            return os.path.join(self.host_root, container_path[len(root) + 1 :])
        return container_path

    def claim(self, row_id: str, container_path: str, note: str = "") -> Claim:
        """Record *container_path* as a path this row may create. Idempotent per path."""
        for existing in self.claims:
            if existing.container_path == container_path:
                return existing
        host = self.host_path(container_path)
        claim = Claim(
            container_path=container_path,
            host_path=host,
            row_id=row_id,
            pre_existed=os.path.exists(host),
            note=note,
        )
        self.claims.append(claim)
        return claim

    def claim_produced(self, row_id: str, container_path: str, since: float) -> Claim | None:
        """Claim a file the job *reported producing*, so it can be cleaned out of a shared dir.

        Some outputs land in a directory that legitimately pre-exists and is shared with the
        maintainer's own data -- a preprocessing report goes to
        ``derivatives/ti-toolbox/reports/sub-<id>/pre_processing_report_<timestamp>.html``
        beside every earlier report. Claiming the *directory* would either delete their reports
        or (because the directory pre-exists) delete nothing, which is how three smoke reports
        accumulated there on 2026-09-03 before this method existed.

        The safety condition is checked, not assumed: the file must exist **and** its mtime must
        be at or after *since* (the job's start), i.e. this run really did write it. A runner
        that reports an input file as an artifact therefore claims nothing.

        Returns the claim, or ``None`` when the file is older than the job (nothing to clean).
        """
        host = self.host_path(container_path)
        try:
            produced = os.path.isfile(host) and os.path.getmtime(host) >= since
        except OSError:
            produced = False
        if not produced:
            return None
        for existing in self.claims:
            if existing.container_path == container_path:
                return existing
        claim = Claim(
            container_path=container_path,
            host_path=host,
            row_id=row_id,
            pre_existed=False,
            note=f"produced by this run (mtime >= job start {since:.0f})",
        )
        self.claims.append(claim)
        return claim

    def pre_existing(self, row_id: str) -> list[Claim]:
        return [c for c in self.claims if c.row_id == row_id and c.pre_existed]

    def remove_created(self, row_id: str | None = None) -> list[Claim]:
        """Delete claims that did not pre-exist. Returns the claims actually removed."""
        removed: list[Claim] = []
        if self.keep:
            return removed
        # Deepest first, so a nested claim never disappears under a parent mid-loop.
        targets = [
            c
            for c in self.claims
            if not c.pre_existed and not c.removed and (row_id is None or c.row_id == row_id)
        ]
        for claim in sorted(targets, key=lambda c: c.host_path.count("/"), reverse=True):
            path = claim.host_path
            if not (os.path.exists(path) or os.path.islink(path)):
                # The row never created it (cancelled before writing, or refused outright).
                # Marking it "removed" would claim a deletion that never happened.
                claim.note = (claim.note + " | never created").strip(" |")
                continue
            try:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except OSError as exc:  # a busy/permission failure must not hide the row's result
                claim.note = (claim.note + f" | cleanup failed: {exc}").strip(" |")
                continue
            claim.removed = True
            removed.append(claim)
        return removed

    def to_json(self) -> str:
        return json.dumps(
            {
                "container_root": self.container_root,
                "host_root": self.host_root,
                "keep": self.keep,
                "claims": [asdict(c) for c in self.claims],
            },
            indent=2,
            sort_keys=True,
        )

    def write(self, path: str) -> str:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_json() + "\n")
        return path
