"""Assemble the MNE forward/source-space/morph files from a SimNIBS leadfield.

Run as a child process of :func:`tit.source.forward.prepare_forward`::

    <simnibs python> -m tit.source._prepare_forward \\
        <m2m_dir> <leadfield.hdf5> <info.fif> <trans.fif> --fsaverage 5

This is a drop-in replacement for SimNIBS's own ``prepare_eeg_forward mne``
console script -- same inputs, same call into
:func:`simnibs.eeg.forward.make_forward`, same outputs written next to the
leadfield -- with one addition:
:func:`tit.source._simnibs_compat.ensure_simnibs_eeg_compat` runs first.

Why not just call the console script (the failure this prevents)
----------------------------------------------------------------
``prepare_eeg_forward`` is a shell wrapper around ``python -E``, which ignores
``PYTHONPATH`` and every other ``PYTHON*`` variable, so there is no way to get
a compatibility shim into that interpreter from outside.  On the image's stack
SimNIBS's own bridge dies with ``AttributeError: No mne.source_space attribute
_complete_source_space_info`` about ten minutes in, *after* the FEM leadfield
has been computed.  Calling the underlying function ourselves keeps the work in
a separate process (the gain matrix is ~0.9 GB for a 75-channel net) while
letting the shim run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tit.source._prepare_forward",
        description="Write the MNE forward, source space and fsaverage morph "
        "for a SimNIBS point-electrode EEG leadfield.",
    )
    parser.add_argument("m2m_dir", help="the subject's m2m_<id> directory")
    parser.add_argument("leadfield", help="point-electrode leadfield HDF5")
    parser.add_argument("info", help="mne.Info FIF holding the net's montage")
    parser.add_argument("trans", help="head<->MRI transform FIF")
    parser.add_argument(
        "--fsaverage",
        type=int,
        default=5,
        help="fsaverage subdivision to morph to (5, 6 or 7)",
    )
    parser.add_argument(
        "--no-average-ref",
        action="store_true",
        help="do not apply an average reference to the gain matrix",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    from tit.source._simnibs_compat import ensure_simnibs_eeg_compat

    applied = ensure_simnibs_eeg_compat()
    if applied:
        print(f"SimNIBS EEG-bridge shims applied: {', '.join(applied)}", flush=True)

    from simnibs.eeg.forward import make_forward

    make_forward(
        m2m_dir=Path(args.m2m_dir),
        fname_leadfield=Path(args.leadfield).resolve(),
        out_format="mne",
        info=args.info,
        trans=args.trans,
        morph_to_fsaverage=args.fsaverage,
        apply_average_proj=not args.no_average_ref,
        write=True,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
