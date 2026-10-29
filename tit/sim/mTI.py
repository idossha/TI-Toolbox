#!/usr/bin/env simnibs_python
"""N-channel Multi-channel Temporal Interference (mTI) simulation.

Implements :class:`mTISimulation`, the concrete ``BaseSimulation`` subclass
for multi-channel TI stimulation with an arbitrary even number of channels
(4, 6, 8, ...):

* Each channel produces one HF E-field via SimNIBS TDCS.
* Each beating pair's two channels are combined into an intermediate TI
  vector field, saved for inspection only.
* The final mTI envelope is the joint envelope maximum
  (:func:`tit.calc.envelope_max`) over all N channel fields
  jointly -- *not* a recursive TI-of-TI combination of the intermediate
  fields above (that approximation is physically invalid).
* Channels are paired positionally: each two consecutive channels form a
  beating pair at a common difference frequency (channels 1 and 2 the first
  pair, 3 and 4 the second, and so on; on disk the channels are lettered
  ``A``, ``B``, ``C``, ``D`` ...).

Example with 4 channels (on disk A/B/C/D)::

    TI_AB = _ti_vectors([E_A, E_B])            # intermediate, inspection only
    TI_CD = _ti_vectors([E_C, E_D])            # intermediate, inspection only
    mTI   = envelope_max([E_A, E_B, E_C, E_D])

See Also
--------
BaseSimulation : Abstract base class providing the ``run`` template.
TISimulation : Standard two-channel TI variant.
SimulationConfig : Configuration consumed by the simulation.
run_simulation : Top-level orchestration that dispatches to this class.
"""

import glob
import os
import string
from copy import deepcopy

from simnibs import mesh_io, sim_struct

from tit import constants as const
from tit.calc import envelope_max
from tit.sim.base import BaseSimulation
from tit.sim.config import SimulationMode
from tit.sim.utils import (
    extract_fields,
    finish_t1_to_mni,
    safe_move,
    start_t1_to_mni,
    transform_dirs_to_nifti,
)


def _ti_vectors(fields):
    """TI vectors: the envelope maximum times its (oriented) maximising direction."""
    amp, direction = envelope_max(fields, return_direction=True)
    return amp[:, None] * direction


class mTISimulation(BaseSimulation):
    """Run a single N-channel mTI simulation (N >= 4, even).

    Pipeline
    --------
    1. Set up BIDS output directory structure.
    2. Visualize electrode placement.
    3. Build SimNIBS SESSION (N TDCS lists), run FEM.
    4. Compute each beating pair's intermediate TI vector field (adjacent
       channels, saved for inspection only).
    5. Compute final ``mTI_max`` from the verified
       modulation-depth envelope over all N channel fields jointly, plus
       its orientation-averaged companion ``TI_avg`` and the ``hf_peak``/
       ``hf_sar``/``hf_power_density`` kHz-exposure safety maps (always over
       all N fields).
    6. Extract GM/WM meshes, convert to NIfTI, organize outputs.

    See Also
    --------
    BaseSimulation : Parent class with shared setup and template ``run``.
    TISimulation : Standard two-channel variant.
    """

    @property
    def _simulation_mode(self):
        """Return ``SimulationMode.MTI``."""
        return SimulationMode.MTI

    @property
    def _montage_type_label(self) -> str:
        """Return ``'mTI'``."""
        return "mTI"

    @property
    def _montage_imgs_key(self) -> str:
        """Return ``'mti_montage_imgs'``."""
        return "mti_montage_imgs"

    # ── Session building ────────────────────────────────────────────────────────────────

    def _build_session(self, output_dir: str) -> sim_struct.SESSION:
        """Build SimNIBS SESSION for N-channel mTI.

        Parameters
        ----------
        output_dir : str
            Directory where SimNIBS writes FEM output.

        Returns
        -------
        sim_struct.SESSION
            Configured session with N TDCS lists (one per channel).
        """
        S = self._init_session(output_dir)
        n_pairs = self.montage.num_pairs

        for i in range(n_pairs):
            self._add_electrode_pair(
                S,
                self.montage.electrode_pairs[i],
                self.config.intensities[i],
                pair_index=i,
            )

        return S

    # ── Post-processing ────────────────────────────────────────────────────────────────

    def _post_process(self, dirs: dict) -> str:
        """Compute mTI fields, extract meshes, convert to NIfTI.

        Parameters
        ----------
        dirs : dict
            Directory mapping returned by ``setup_montage_directories``.

        Returns
        -------
        str
            Path to the output mTI mesh file.

        Raises
        ------
        ValueError
            If the montage has more than 26 channels (A-Z limit).
        """
        sid = self.config.subject_id
        name = self.montage.name
        n_pairs = self.montage.num_pairs
        if n_pairs > 26:
            raise ValueError(
                f"mTI supports at most 26 pairs (A-Z labeling), got {n_pairs}"
            )
        letters = list(string.ascii_uppercase[:n_pairs])

        meshes = self._cropped_carriers(dirs["hf_dir"], n_pairs)
        e_fields = [m.field["E"].value for m in meshes]

        # Save intermediate pairwise TI fields (adjacent pairs)
        ti_pair_suffixes = []
        for i in range(0, n_pairs, 2):
            suffix = f"TI_{letters[i]}{letters[i + 1]}"
            ti_pair_suffixes.append(suffix)
            ti_vecs = _ti_vectors([e_fields[i], e_fields[i + 1]])
            self._save_ti_vectors(
                meshes[0], ti_vecs, dirs["ti_mesh"], f"{name}_{suffix}.msh"
            )

        # Final mTI: the envelope of all N channel fields jointly -- not a
        # recursive TI-of-TI combination of the pairwise fields saved above.
        mti_path = os.path.join(dirs["mti_mesh"], f"{name}_mTI.msh")
        self._write_volume_mesh(meshes, const.FIELD_MTI_MAX, mti_path)
        self._write_ti_normal(
            dirs["hf_dir"],
            n_pairs,
            os.path.join(dirs["mti_mesh"], f"{name}_mTI_normal.msh"),
        )

        # Field extraction — mTI mesh and all intermediate TI meshes
        self.logger.info("Field extraction: Started")
        extract_fields(
            mti_path, dirs["mti_mesh"], f"{name}_mTI", self.m2m_dir, sid, self.logger
        )
        for suffix in ti_pair_suffixes:
            extract_fields(
                os.path.join(dirs["ti_mesh"], f"{name}_{suffix}.msh"),
                dirs["ti_mesh"],
                f"{name}_{suffix}",
                self.m2m_dir,
                sid,
                self.logger,
            )
        self.logger.info("Field extraction: \u2713 Complete")

        # Organize files before NIfTI conversion so meshes are in their
        # final directories (hf_mesh/)
        self._organize_files(dirs)

        self._generate_central_surface(mti_path, dirs["mti_surfaces"])

        # T1->MNI is independent of the field meshes; start it in the
        # background so it overlaps the mesh-to-NIfTI conversions.
        t1_proc = start_t1_to_mni(self.m2m_dir, sid) if self.config.map_to_mni else None

        self.logger.info("NIfTI transformation: Started")
        transform_dirs_to_nifti(
            [
                {"mesh_dir": dirs["mti_mesh"], "output_dir": dirs["mti_niftis"]},
                {
                    "mesh_dir": dirs["hf_mesh"],
                    "output_dir": dirs["hf_niftis"],
                    "fields": ["magnE"],
                },
            ],
            self.m2m_dir,
            self.logger,
            map_to_mni=self.config.map_to_mni,
        )
        self.logger.info("NIfTI transformation: \u2713 Complete")

        if t1_proc is not None:
            finish_t1_to_mni(t1_proc, self.logger)

        return mti_path

    def _save_ti_vectors(
        self, base_mesh, ti_vectors, output_dir: str, filename: str
    ) -> None:
        """Save an intermediate TI vector field mesh."""
        mout = deepcopy(base_mesh)
        mout.elmdata = []
        mout.add_element_field(ti_vectors, "TI_vectors")
        path = os.path.join(output_dir, filename)
        mesh_io.write_msh(mout, path)
        mout.view(visible_tags=[1002, 1006], visible_fields="TI_vectors").write_opt(
            path
        )
        self.logger.debug(f"Saved: {path}")

    def _organize_files(self, dirs: dict) -> None:
        """Move HF files, renaming channels ``1..N`` to ``A..Z`` for mTI convention."""
        hf = dirs["hf_dir"]
        n_pairs = self.montage.num_pairs
        letters = string.ascii_uppercase

        cond = self.config.conductivity
        for i in range(1, n_pairs + 1):
            ltr = letters[i - 1]
            for ext in (".geo", f"{cond}.msh", f"{cond}.msh.opt"):
                # "TDCS_1_", not "TDCS_1": channel 1 must not take channels 10..19.
                for f in glob.glob(os.path.join(hf, f"*TDCS_{i}_*{ext}")):
                    new_name = os.path.basename(f).replace(f"TDCS_{i}", f"TDCS_{ltr}")
                    safe_move(f, os.path.join(dirs["hf_mesh"], new_name))

        # Move surface overlays (already consumed for TI_normal, kept for
        # inspection and fsaverage projection)
        overlays = os.path.join(hf, "subject_overlays")
        if os.path.isdir(overlays):
            for fname in os.listdir(overlays):
                safe_move(
                    os.path.join(overlays, fname),
                    os.path.join(dirs["mti_surface_overlays"], fname),
                )
            os.rmdir(overlays)

        safe_move(
            os.path.join(hf, "fields_summary.txt"),
            os.path.join(dirs["hf_analysis"], "fields_summary.txt"),
        )

        for pattern in ("simnibs_simulation_*.log", "simnibs_simulation_*.mat"):
            for f in glob.glob(os.path.join(hf, pattern)):
                safe_move(
                    f,
                    os.path.join(dirs["documentation"], os.path.basename(f)),
                )
