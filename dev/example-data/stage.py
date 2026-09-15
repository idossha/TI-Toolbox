#!/usr/bin/env python3
"""Build the content-addressed assets behind tit/examples/catalog.json from the SimNIBS example zip.

    python3 dev/example-data/stage.py --zip simnibs4_examples.zip [--out <dir>] [--write-catalog]

The upstream release (``simnibs/example-dataset`` v4.1, ``simnibs4_examples.zip``, sha256-pinned
below) is the single source. From it this script produces every catalogue file:

    sub-ernie_T1w.nii.gz   <- org/ernie_T1.nii.gz        (raw, as-is)
    sub-ernie_T2w.nii.gz   <- org/ernie_T2.nii.gz        (raw, as-is)
    sub-MNI152_T1w.nii.gz  <- m2m_MNI152/T1.nii.gz       (the zip ships no raw MNI152 scan; charm's
                                                          conformed T1 of the template is the input)
    m2m_ernie.tar.gz       <- m2m_ernie/**               (one deterministic tarball per head model)
    m2m_MNI152.tar.gz      <- m2m_MNI152/**

and copies each to ``<out>/<sha256>`` -- the asset name the store uses (3D Slicer's SlicerDataStore
layout, as Tetravox's sample store). ``--write-catalog`` then fills ``bytes``/``sha256``/``url`` in
the catalogue from what was built, so the catalogue never carries a hash nobody computed.
``publish.sh`` uploads the directory.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "tit" / "examples" / "catalog.json"
ZIP_SHA256 = "a7e729db1306657f5c4f9a5dee493e22eb5a4c6fb2fd62f8ec81dc0cca4196e6"

#: catalogue file name -> zip member (plain copy)
COPIES = {
    "sub-ernie_T1w.nii.gz": "org/ernie_T1.nii.gz",
    "sub-ernie_T2w.nii.gz": "org/ernie_T2.nii.gz",
    "sub-MNI152_T1w.nii.gz": "m2m_MNI152/T1.nii.gz",
}
#: catalogue file name -> zip prefix packed as a tarball keeping that prefix
TARBALLS = {"m2m_ernie.tar.gz": "m2m_ernie/", "m2m_MNI152.tar.gz": "m2m_MNI152/"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_tarball(zf: zipfile.ZipFile, prefix: str, dest: Path) -> None:
    """Deterministic: members in zip order, mtime 0, root-owned, gzip without a timestamp."""
    with open(dest, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=6) as gz:
        with tarfile.open(fileobj=gz, mode="w|") as tar:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.startswith(prefix):
                    continue
                ti = tarfile.TarInfo(info.filename)
                ti.size = info.file_size
                ti.mtime = 0
                ti.mode = 0o644
                with zf.open(info) as src:
                    tar.addfile(ti, src)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", default=str(ROOT / "dev" / "example-data" / "store"))
    ap.add_argument("--build", default=None, help="where the named files are built (default <out>/build)")
    ap.add_argument("--write-catalog", action="store_true")
    args = ap.parse_args()
    zip_path = Path(args.zip)
    out = Path(args.out)
    build = Path(args.build) if args.build else out / "build"
    out.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)

    got = sha256(zip_path)
    if got != ZIP_SHA256:
        print(f"zip sha256 {got} != pinned {ZIP_SHA256}")
        return 1

    with zipfile.ZipFile(zip_path) as zf:
        for name, member in COPIES.items():
            dst = build / name
            if not dst.exists():
                with zf.open(member) as src, open(dst, "wb") as o:
                    shutil.copyfileobj(src, o, 1 << 20)
            print(f"built    {name}  ({dst.stat().st_size} B)")
        for name, prefix in TARBALLS.items():
            dst = build / name
            if not dst.exists():
                build_tarball(zf, prefix, dst)
            print(f"built    {name}  ({dst.stat().st_size} B)")

    catalog = json.loads(CATALOG.read_text())
    store = catalog["store"]
    for sample in catalog["samples"]:
        for f in sample["files"]:
            src = build / f["name"]
            digest = sha256(src)
            size = src.stat().st_size
            if args.write_catalog:
                f["bytes"], f["sha256"], f["url"] = size, digest, store + digest
            elif (size, digest) != (f["bytes"], f["sha256"]):
                print(f"MISMATCH {sample['id']}/{f['name']}  {size} B {digest[:12]} vs catalogue {f['bytes']} B {f['sha256'][:12]}")
                return 1
            asset = out / digest
            if not asset.exists():
                shutil.copyfile(src, asset)
            print(f"staged   {digest[:12]}  {f['name']}  ({size} B)")
    if args.write_catalog:
        CATALOG.write_text(json.dumps(catalog, indent=2) + "\n")
        print(f"wrote {CATALOG}")
    print(f"{len([p for p in out.iterdir() if p.is_file()])} assets in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
