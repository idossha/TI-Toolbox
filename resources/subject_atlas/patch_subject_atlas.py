"""Patch SimNIBS 4.6 subject_atlas CLI bug.

SimNIBS 4.6 renamed the -m/--m2mpath argument to a positional 'subid'
but the error message in main() still references args.m2mpath, causing
an AttributeError when the directory check fails.

Fix: replace args.m2mpath with args.subid in the error message.

Usage (run once after SimNIBS install):
    simnibs_python resources/subject_atlas/patch_subject_atlas.py
"""

import sys
from pathlib import Path


def find_subject_atlas_py():
    """Locate the installed subject_atlas.py."""
    import simnibs.cli.subject_atlas as mod
    return Path(mod.__file__)


BUGGY = "args.m2mpath"
FIXED = "args.subid"


def patch():
    path = find_subject_atlas_py()
    original = path.read_text()

    if BUGGY not in original:
        if 'raise IOError("Could not find directory: {0}".format(args.subid))' in original:
            print(f"Already patched: {path}")
            return True
        print(f"ERROR: Could not find buggy pattern in {path}", file=sys.stderr)
        return False

    patched = original.replace(BUGGY, FIXED)
    path.write_text(patched)
    print(f"Patched: {path}")
    print("Patch verified successfully.")
    return True


if __name__ == "__main__":
    sys.exit(0 if patch() else 1)
