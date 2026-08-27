#!/usr/bin/env python3
"""Build the seed project that every hub user starts from.

Copies the minimum of an existing TI-Toolbox project needed to run the example
notebook (anatomy + m2m head model + toolbox config) into SEED_DIR:

    python3 make_seed.py /path/to/000 /srv/tit-seed/000 --subject ernie
    python3 make_seed.py /path/to/000 /srv/tit-seed/000 --subject ernie --with-leadfields

Size: ~1.5 GB (ernie), +3.3 GB with leadfields (needed for ex-search only).
"""
import argparse
import shutil
import sys
from pathlib import Path


def copy(src: Path, dst: Path, required: bool = True) -> None:
    if not src.exists():
        if required:
            sys.exit(f"missing: {src}")
        print(f"skip (absent): {src}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    print(f"copied {src} -> {dst}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path, help="existing project root (e.g. .../000)")
    ap.add_argument("seed", type=Path, help="output seed directory (SEED_DIR in .env)")
    ap.add_argument("--subject", default="ernie")
    ap.add_argument("--with-leadfields", action="store_true", help="include derivatives/SimNIBS/sub-X/leadfields")
    a = ap.parse_args()

    src, dst, s = a.project, a.seed, a.subject
    copy(src / "dataset_description.json", dst / "dataset_description.json")
    copy(src / f"sub-{s}", dst / f"sub-{s}")
    copy(src / "derivatives/SimNIBS" / f"sub-{s}" / f"m2m_{s}", dst / "derivatives/SimNIBS" / f"sub-{s}" / f"m2m_{s}")
    copy(src / "code/ti-toolbox/config", dst / "code/ti-toolbox/config")
    copy(src / "derivatives/ti-toolbox/dataset_description.json",
         dst / "derivatives/ti-toolbox/dataset_description.json", required=False)
    if a.with_leadfields:
        copy(src / "derivatives/SimNIBS" / f"sub-{s}" / "leadfields", dst / "derivatives/SimNIBS" / f"sub-{s}" / "leadfields")
    # A fresh project must not think it already ran things it did not.
    status = dst / "code/ti-toolbox/config/project_status.json"
    if status.exists():
        status.write_text('{"example_data_copied": true}\n')
    print("seed ready:", dst)


if __name__ == "__main__":
    main()
