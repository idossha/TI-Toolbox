"""Write the streamline files ``desktop/tests/e2e/real/network-own-file.spec.ts`` loads, into a folder.

From a subject's own tractogram and network: ``own_spec_tck.tck`` and ``own_spec_trx.trx`` hold the
streamlines of the given region pairs, ``own_spec_shifted.tck`` the same 200 mm to the side, and
``own_spec_empty.tck`` no streamlines.

Run in the image, with paths as the container sees them:
    simnibs_python dev/export_own_network_fixture.py <project> <subject> <out> a|b [c|d ...]
"""

from __future__ import annotations

import os
import sys

import numpy as np


def main(project: str, subject: str, out: str, pairs: list[str]) -> None:
    import nibabel as nib
    from dipy.io.stateful_tractogram import Space, StatefulTractogram
    from dipy.io.streamline import save_tractogram as dipy_save

    from tit.paths import get_path_manager
    from tit.tract.config import Selection
    from tit.tract.io import load_streamlines, save_tractogram
    from tit.tract.network import select

    pm = get_path_manager(project)
    tract_dir = pm.tractography(subject)
    streamlines = load_streamlines(os.path.join(tract_dir, "tractogram.trx"))
    with np.load(os.path.join(tract_dir, "network.npz"), allow_pickle=False) as data:
        names = [str(n) for n in data["names"]]
        labels, edge_id = data["labels"], data["edge_id"]
    selection = Selection(
        name="own_spec", kind="edges", pairs=[p.split("|") for p in pairs]
    )
    picked = [
        streamlines[i]
        for i in np.flatnonzero(select(selection, labels, names, edge_id))
    ]
    ref = nib.load(pm.t1(subject))
    os.makedirs(out, exist_ok=True)
    save_tractogram(os.path.join(out, "own_spec_tck.tck"), picked, ref)
    save_tractogram(os.path.join(out, "own_spec_trx.trx"), picked, ref)
    save_tractogram(
        os.path.join(out, "own_spec_shifted.tck"),
        [s + np.array([200.0, 0.0, 0.0]) for s in picked],
        ref,
    )
    dipy_save(
        StatefulTractogram([], ref, Space.RASMM),
        os.path.join(out, "own_spec_empty.tck"),
        bbox_valid_check=False,
    )
    print(f"{len(picked)} streamlines in {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
