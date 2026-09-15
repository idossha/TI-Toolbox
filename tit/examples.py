"""Fetch the SimNIBS example subject (``ernie``) into a project.

The bundled ``resources/example_data`` holds raw T1/T2 only; the optimizer, simulator and
analyzer need a finished ``m2m_ernie`` head model, which charm takes 1-2 h to build. The
SimNIBS example dataset (<https://github.com/simnibs/example-dataset>, GPL-3.0 -- licence vetted
in ``tit/scene/guide/PROVENANCE.md``) ships one ready-made, so :func:`fetch_ernie` downloads that
release once and lays it into the BIDS layout :class:`tit.paths.PathManager` expects::

    <project>/sub-ernie/anat/sub-ernie_T1w.nii.gz   (+ _T2w)
    <project>/derivatives/SimNIBS/sub-ernie/m2m_ernie/

Three entry points call it: ``python -m tit.examples --project DIR``, the server route
``POST /api/project/example-subject`` (a ``project_init`` job) and the desktop Overview page's
**Add example subject** button. Stdlib only, so it runs on the host as well as in the container.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

SUBJECT = "ernie"
RELEASE_URL = (
    "https://github.com/simnibs/example-dataset/releases/download/v4.1/simnibs4_examples.zip"
)
RELEASE_SHA256 = "a7e729db1306657f5c4f9a5dee493e22eb5a4c6fb2fd62f8ec81dc0cca4196e6"
RELEASE_SIZE_MB = 1066
#: The archive has no top-level folder: ``m2m_ernie/``, ``m2m_MNI152/``, ``org/`` sit at its root.
_M2M_PREFIX = f"m2m_{SUBJECT}/"
_ANAT = {
    f"org/{SUBJECT}_T1.nii.gz": f"sub-{SUBJECT}_T1w.nii.gz",
    f"org/{SUBJECT}_T2.nii.gz": f"sub-{SUBJECT}_T2w.nii.gz",
}


def _m2m_dir(project_dir: Path) -> Path:
    return project_dir / "derivatives" / "SimNIBS" / f"sub-{SUBJECT}" / f"m2m_{SUBJECT}"


def _download(url: str, dest: Path, *, log=print) -> None:
    """Stream *url* to *dest*, printing whole-percent progress."""
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:  # noqa: S310 - pinned https URL
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last = -1
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                if pct != last:
                    log(f"download {pct}%", flush=True)
                    last = pct
    if not total:
        log("download 100%", flush=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_member(zf: zipfile.ZipFile, member: zipfile.ZipInfo, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out, 1 << 20)


def _register(project_dir: Path) -> None:
    """Record the subject in the manifests ``tit.project_init`` writes (best effort)."""
    from tit.project_init.initializer import (
        initialize_dataset_description,
        initialize_derivative_dataset_description,
        initialize_project_status,
        load_project_status,
        update_project_status,
    )

    initialize_dataset_description(project_dir)
    initialize_derivative_dataset_description(project_dir, "SimNIBS")
    initialize_project_status(project_dir)
    status = load_project_status(project_dir)
    subjects = list(status.get("example_subjects") or [])
    if SUBJECT not in subjects:
        subjects.append(SUBJECT)
    update_project_status(
        project_dir,
        {"example_subjects": subjects, "example_subject_source": RELEASE_URL},
    )


def fetch_ernie(project_dir: str | Path, *, force: bool = False, log=print) -> Path:
    """Download the SimNIBS example subject into *project_dir*; return its ``m2m_ernie`` path.

    Idempotent: returns immediately when ``m2m_ernie`` already exists unless *force*. The archive
    (~1 GB) is verified against :data:`RELEASE_SHA256` before anything is written into the
    project; on a mismatch nothing is touched and :class:`ValueError` is raised.
    """
    project_dir = Path(project_dir).expanduser().resolve()
    m2m = _m2m_dir(project_dir)
    if m2m.is_dir() and not force:
        log(f"example subject already present: {m2m}", flush=True)
        return m2m

    with tempfile.TemporaryDirectory(prefix="tit-examples-") as tmp:
        archive = Path(tmp) / "simnibs4_examples.zip"
        log(f"downloading {RELEASE_URL} (~{RELEASE_SIZE_MB} MB)", flush=True)
        _download(RELEASE_URL, archive, log=log)
        digest = _sha256(archive)
        if digest != RELEASE_SHA256:
            raise ValueError(
                f"sha256 mismatch for {RELEASE_URL}: got {digest}, expected {RELEASE_SHA256}"
            )
        log("checksum ok; extracting", flush=True)

        if m2m.exists():
            shutil.rmtree(m2m)
        anat = project_dir / f"sub-{SUBJECT}" / "anat"
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            n = 0
            for info in members:
                name = info.filename
                if info.is_dir():
                    continue
                if name.startswith(_M2M_PREFIX):
                    rel = name[len(_M2M_PREFIX):]
                    if ".." in rel.split("/"):
                        raise ValueError(f"unsafe archive member: {name}")
                    _extract_member(zf, info, m2m / rel)
                    n += 1
                elif name in _ANAT:
                    _extract_member(zf, info, anat / _ANAT[name])
                    n += 1
        if n == 0 or not m2m.is_dir():
            raise ValueError(f"archive has no {_M2M_PREFIX} members: {RELEASE_URL}")
        log(f"extracted {n} files", flush=True)

    _register(project_dir)
    log(f"example subject ready: {m2m}", flush=True)
    return m2m


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tit.examples",
        description="Download the SimNIBS example subject (ernie) into a project.",
    )
    parser.add_argument("--project", required=True, help="BIDS project root")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args(argv)
    try:
        fetch_ernie(args.project, force=args.force)
    except (OSError, ValueError) as exc:
        print(f"tit.examples: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
