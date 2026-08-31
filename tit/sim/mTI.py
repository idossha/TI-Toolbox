#!/usr/bin/env simnibs_python
"""N-pair Multi-channel Temporal Interference (mTI) simulation.

Implements :class:`mTISimulation`, the concrete ``BaseSimulation`` subclass
for multi-channel TI stimulation with an arbitrary even number of electrode
pairs (4, 6, 8, ...):

* Each pair produces one HF E-field via SimNIBS TDCS.
* Adjacent pairs are combined into intermediate 2-pair TI vector fields,
  saved for inspection only.
* The final mTI envelope is the verified K-pair modulation-depth envelope
  (:func:`tit.calc.get_mTI_vectors`) over all N carrier fields jointly --
  *not* a recursive binary-tree TI-of-TI combination of the intermediate
  fields above (that approximation is deprecated; see
  :func:`tit.calc.get_nTI_vectors`).
* Channels are paired positionally: each two consecutive channels share
  a carrier and beat against each other (A&B on the first carrier, C&D
  on the second, and so on).

Example with 4 channels (A/B/C/D)::

    TI_AB = TI(E_A, E_B)                       # intermediate, inspection only
    TI_CD = TI(E_C, E_D)                       # intermediate, inspection only
    mTI   = get_mTI_vectors([E_A, E_B, E_C, E_D])

See Also
--------
BaseSimulation : Abstract base class providing the ``run`` template.
TISimulation : Standard 2-pair TI variant.
SimulationConfig : Configuration consumed by the simulation.
run_simulation : Top-level orchestration that dispatches to this class.
"""

import glob
import os
import string
from copy import deepcopy

import numpy as np
from simnibs import mesh_io, sim_struct
from simnibs.utils import TI_utils as TI

from tit import constants as const
from tit.calc import get_mTI_dir, get_mTI_vectors, get_TI_avg, get_TI_vectors
from tit.fields import hf_peak, hf_sar
from tit.sim.base import BaseSimulation
from tit.sim.config import SimulationMode
from tit.sim.utils import (
    extract_fields,
    finish_t1_to_mni,
    safe_move,
    start_t1_to_mni,
    transform_dirs_to_nifti,
)

# Brain tissue crop mask — ranges defined in constants.BRAIN_TISSUE_TAG_RANGES
_TAGS_KEEP = np.hstack([np.arange(lo, hi) for lo, hi in const.BRAIN_TISSUE_TAG_RANGES])


class mTISimulation(BaseSimulation):
    """Run a single N-pair mTI simulation (N >= 4, even).

    Pipeline
    --------
    1. Set up BIDS output directory structure.
    2. Visualize electrode placement.
    3. Build SimNIBS SESSION (N TDCS lists), run FEM.
    4. Compute intermediate 2-pair TI vector fields (adjacent pairings,
       saved for inspection only).
    5. Compute final ``mTI_max`` from the verified multi-carrier
       modulation-depth envelope over all N channel fields jointly, plus
       its orientation-averaged companion ``TI_avg`` and the ``hf_peak``/
       ``hf_sar`` kHz-exposure safety maps (always over all N fields).
    6. Extract GM/WM meshes, convert to NIfTI, organize outputs.

    See Also
    --------
    BaseSimulation : Parent class with shared setup and template ``run``.
    TISimulation : Standard 2-pair variant.
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
        """Build SimNIBS SESSION for N-pair mTI.

        Parameters
        ----------
        output_dir : str
            Directory where SimNIBS writes FEM output.

        Returns
        -------
        sim_struct.SESSION
            Configured session with N TDCS lists (one per pair).
        """
        S = self._init_session(output_dir)
        n_pairs = self.montage.num_pairs

        for i in range(n_pairs):
            self._add_electrode_pair(
                S, self.montage.electrode_pairs[i], self.config.intensities[i]
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
            If the montage has more than 26 electrode pairs (A-Z limit).
        """
        sid = self.config.subject_id
        cond = self.config.conductivity
        name = self.montage.name
        n_pairs = self.montage.num_pairs
        if n_pairs > 26:
            raise ValueError(
                f"mTI supports at most 26 pairs (A-Z labeling), got {n_pairs}"
            )
        letters = list(string.ascii_uppercase[:n_pairs])

        # Load and crop all N HF meshes
        meshes = []
        for i in range(1, n_pairs + 1):
            m = mesh_io.read_msh(
                os.path.join(dirs["hf_dir"], f"{sid}_TDCS_{i}_{cond}.msh")
            )
            meshes.append(m.crop_mesh(tags=_TAGS_KEEP))

        # Extract E-field arrays
        e_fields = [m.field["E"].value for m in meshes]

        # Save intermediate pairwise TI fields (adjacent pairs)
        ti_pair_suffixes = []
        for i in range(0, n_pairs, 2):
            ltr1, ltr2 = letters[i], letters[i + 1]
            suffix = f"TI_{ltr1}{ltr2}"
            ti_pair_suffixes.append(suffix)
            ti_vecs = get_TI_vectors(e_fields[i], e_fields[i + 1])
            self._save_ti_vectors(
                meshes[0], ti_vecs, dirs["ti_mesh"], f"{name}_{suffix}.msh"
            )

        # Final mTI: verified K-pair modulation-depth envelope over all N
        # carrier fields jointly (tit.calc.get_mTI_vectors) -- not a
        # recursive binary-tree TI-of-TI combination of the intermediate
        # pairwise fields saved above (that approximation is deprecated;
        # see tit.calc.get_nTI_vectors). Channels are paired positionally:
        # each two consecutive channels share a carrier.
        selected = set(self.config.output_fields)

        mout = deepcopy(meshes[0])
        mout.elmdata = []
        if const.FIELD_TI_MAX in selected:
            mti_vectors = get_mTI_vectors(e_fields)
            mti_field = np.linalg.norm(mti_vectors, axis=1)
            mout.add_element_field(mti_field, const.FIELD_MTI_MAX)
        if const.FIELD_TI_AVG in selected:
            # TI_avg: orientation-averaged companion to mTI_max, over all N
            # channel fields jointly (tit.calc.get_TI_avg).
            mti_avg = get_TI_avg(e_fields)
            mout.add_element_field(mti_avg, const.FIELD_TI_AVG)
        if const.FIELD_HF_PEAK in selected:
            # Carrier-exposure safety map (Cassarà 2025): peak carrier field,
            # over all N per-pair carrier fields.
            mout.add_element_field(hf_peak(*e_fields), const.FIELD_HF_PEAK)
        if const.FIELD_HF_SAR in selected:
            # Carrier-exposure safety map (Cassarà 2025): heating driver.
            mout.add_element_field(hf_sar(*e_fields), const.FIELD_HF_SAR)

        view_field = (
            const.FIELD_MTI_MAX
            if const.FIELD_TI_MAX in selected
            else next(iter(selected))
        )
        mti_path = os.path.join(dirs["mti_mesh"], f"{name}_mTI.msh")
        mesh_io.write_msh(mout, mti_path)
        mout.view(visible_tags=[1002, 1006], visible_fields=view_field).write_opt(
            mti_path
        )
        self.logger.info(f"mTI mesh saved: {mti_path}")

        self._calculate_mti_normal(dirs["hf_dir"], dirs["mti_mesh"], name, n_pairs)

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
        t1_proc = start_t1_to_mni(self.m2m_dir, sid)

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
        )
        self.logger.info("NIfTI transformation: \u2713 Complete")

        finish_t1_to_mni(t1_proc, self.logger)

        return mti_path

    def _calculate_mti_normal(
        self, hf_dir: str, output_dir: str, montage_name: str, n_pairs: int
    ) -> None:
        """Compute ``TI_normal`` on the cortical surface for mTI.

        Mirrors ``TISimulation._calculate_ti_normal``: reads the N
        per-channel SimNIBS central-surface overlays and evaluates the
        multi-carrier envelope along the node normals
        (:func:`tit.calc.get_mTI_dir`) instead of maximizing over
        direction.
        """
        sid = self.config.subject_id
        cond = self.config.conductivity
        overlays = os.path.join(hf_dir, "subject_overlays")

        cms = [
            mesh_io.read_msh(
                os.path.join(overlays, f"{sid}_TDCS_{i}_{cond}_central.msh")
            )
            for i in range(1, n_pairs + 1)
        ]

        normals = cms[0].nodes_normals().value
        if "E" in cms[0].field:
            e_fields = [cm.field["E"].value for cm in cms]
        else:
            e_fields = [
                cm.field["E_normal"].value.reshape(-1, 1) * normals for cm in cms
            ]

        ti_normal = get_mTI_dir(e_fields, normals)

        mout = deepcopy(cms[0])
        mout.nodedata = []
        mout.add_node_field(ti_normal, "TI_normal")

        normal_path = os.path.join(output_dir, f"{montage_name}_mTI_normal.msh")
        mesh_io.write_msh(mout, normal_path)
        mout.view(visible_fields=["TI_normal"]).write_opt(normal_path)
        self.logger.debug(f"TI_normal saved: {normal_path}")

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
        """Move HF files, renaming pairs ``1..N`` to ``A..Z`` for mTI convention."""
        hf = dirs["hf_dir"]
        n_pairs = self.montage.num_pairs
        letters = string.ascii_uppercase

        cond = self.config.conductivity
        for i in range(1, n_pairs + 1):
            ltr = letters[i - 1]
            for ext in (".geo", f"{cond}.msh", f"{cond}.msh.opt"):
                for f in glob.glob(os.path.join(hf, f"*TDCS_{i}*{ext}")):
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
