"""Patch SimNIBS 4.6 nan_to_num(copy=None) for numpy 1.x.

SimNIBS 4.6 uses np.nan_to_num(..., copy=None) in transformations.py,
but ships numpy 1.26.4 where copy=None is not supported (numpy 2.x only).
Both SimNIBS and bpy pin numpy<2, so upgrading is not an option.

Fix: replace copy=None with copy=False across all three call sites.

Usage (run once after SimNIBS install):
    simnibs_python /ti-toolbox/resources/patches/patch_nan_to_num.py
"""

import importlib
import sys
from pathlib import Path


def find_transformations_py():
    """Locate the installed transformations.py."""
    import simnibs.utils.transformations as mod
    return Path(mod.__file__)


def patch():
    path = find_transformations_py()
    src = path.read_text()

    if "copy=None" not in src:
        if "copy=False" in src:
            print(f"Already patched: {path}")
            return True
        print(f"No copy=None found in {path} — nothing to patch.")
        return True

    patched = src.replace("copy=None", "copy=False")
    count = src.count("copy=None")
    path.write_text(patched)
    print(f"Patched {count} call(s) in: {path}")

    importlib.reload(importlib.import_module("simnibs.utils.transformations"))
    print("Patch verified successfully.")
    return True


if __name__ == "__main__":
    sys.exit(0 if patch() else 1)
