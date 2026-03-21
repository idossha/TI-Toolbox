"""Patch SimNIBS atlas2subject split_labels bug.

SimNIBS 4.6 has a bug in atlas2subject() where split_labels=True pairs
np.unique(labels) (sorted by packed RGB) with names (annotation order).
These don't match for DK40, causing wrong region-to-mask mappings.

Fix: replace the faulty np.unique-based logic with ctab-based lookup.

Usage (run once after SimNIBS install):
    simnibs_python resources/atlas2subject/patch_atlas2subject.py
"""

import importlib
import re
import sys
from pathlib import Path


def find_transformations_py():
    """Locate the installed transformations.py."""
    import simnibs.utils.transformations as mod
    return Path(mod.__file__)


BUGGY_PATTERN = re.compile(
    r"(\s+)if split_labels:\n"
    r"\1    (?:labels = np\.unique\(labels\)\n\1    )?"
    r"sub_labels\[h\] = \{[^\}]+\}"
)

FIXED_CODE = (
    "{indent}if split_labels:\n"
    "{indent}    sub_labels[h] = {{n: lab_map == i for i, n in enumerate(names)}}"
)


def patch():
    path = find_transformations_py()
    original = path.read_text()

    match = BUGGY_PATTERN.search(original)
    if not match:
        # Check if already patched
        if "lab_map == i for i, n in enumerate(names)" in original:
            print(f"Already patched: {path}")
            return True
        print(f"ERROR: Could not find buggy pattern in {path}", file=sys.stderr)
        return False

    indent = match.group(1)
    fixed = FIXED_CODE.format(indent=indent)
    patched = original[:match.start()] + fixed + original[match.end():]
    path.write_text(patched)
    print(f"Patched: {path}")

    # Verify
    importlib.reload(importlib.import_module("simnibs.utils.transformations"))
    print("Patch verified successfully.")
    return True


if __name__ == "__main__":
    sys.exit(0 if patch() else 1)
