#!/usr/bin/env simnibs_python
"""
2-pair Temporal Interference (TI) simulation.

Session structure mirrors the official SimNIBS TI example:
  - SESSION with two TDCS lists (one per electrode pair)
  - deepcopy pattern for the second pair
  - TI_max computed with TI.get_maxTI on cropped meshes
  - TI_normal computed on cortical surface overlays

Output mesh includes per-pair E-field magnitudes and TI_max,
matching the reference visualisation layout.
"""

import glob
import os
from copy import deepcopy

import numpy as np
from simnibs import mesh_io, sim_struct
from simnibs.utils import TI_utils as TI

from tit import constants as const
from tit.sim.base import BaseSimulation
from tit.sim.config import SimulationMode
from tit.sim.utils import (
    convert_t1_to_mni,
    extract_fields,
    safe_move,
    transform_to_nifti,
)

# Brain tissue crop mask — keeps tissue volume elements and surface elements
# Ranges defined in constants.BRAIN_TISSUE_TAG_RANGES
_TAGS_KEEP = np.hstack([np.arange(lo, hi) for lo, hi in const.BRAIN_TISSUE_TAG_RANGES])


class TISimulation(BaseSimulation):
    """
    Runs a single 2-pair TI simulation.

    Pipeline:
      1. Set up BIDS output directory structure
      2. Visualize electrode placement
      3. Build SimNIBS SESSION, run FEM
      4. Compute TI_max (volume) and TI_normal (surface)
      5. Extract GM/WM meshes, convert to NIfTI, organize outputs
    """

    @property
    def _simulation_mode(self):
        return SimulationMode.TI

    @property
    def _montage_type_label(self) -> str:
        return "TI"

    @property
    def _montage_imgs_key(self) -> str:
        return "ti_montage_imgs"

    # ── Session building ────────────────────────────────────────────────────────────────

    def _build_session(self, output_dir: str) -> sim_struct.SESSION:
        """Build SimNIBS SESSION for 2-pair TI."""
        S = self._init_session(output_dir)

        # Pair 1
        tdcs1 = self._add_electrode_pair(
            S, self.montage.electrode_pairs[0], self.config.intensities[0]
        )

        # Pair 2 — deepcopy from pair 1, update centres and current
        p2_A = self.config.intensities[1] / 1000.0
        tdcs2 = S.add_tdcslist(deepcopy(tdcs1))
        tdcs2.currents = [p2_A, -p2_A]
        tdcs2.electrode[0].centre = self.montage.electrode_pairs[1][0]
        tdcs2.electrode[1].centre = self.montage.electrode_pairs[1][1]

        return S

    # ── Post-processing ────────────────────────────────────────────────────────────────

    def _post_process(self, dirs: dict) -> str:
        sid = self.config.subject_id
        cond = self.config.conductivity
        name = self.montage.name

        # Load and crop HF meshes
        m1 = mesh_io.read_msh(os.path.join(dirs["hf_dir"], f"{sid}_TDCS_1_{cond}.msh"))
        m2 = mesh_io.read_msh(os.path.join(dirs["hf_dir"], f"{sid}_TDCS_2_{cond}.msh"))
        m1 = m1.crop_mesh(tags=_TAGS_KEEP)
        m2 = m2.crop_mesh(tags=_TAGS_KEEP)

        ef1 = m1.field["E"]
        ef2 = m2.field["E"]
        TImax = TI.get_maxTI(ef1.value, ef2.value)

        mout = deepcopy(m1)
        mout.elmdata = []
        mout.add_element_field(TImax, "TI_max")

        ti_path = os.path.join(dirs["ti_mesh"], f"{name}_TI.msh")
        mesh_io.write_msh(mout, ti_path)
        mout.view(visible_tags=[1002, 1006], visible_fields="TI_max").write_opt(ti_path)
        self.logger.info(f"TI_max saved: {ti_path}")

        self._calculate_ti_normal(dirs["hf_dir"], dirs["ti_mesh"], name)

        self.logger.info("Field extraction: Started")
        extract_fields(
            ti_path, dirs["ti_mesh"], f"{name}_TI", self.m2m_dir, sid, self.logger
        )
        self.logger.info("Field extraction: \u2713 Complete")

        # Organize files before NIfTI conversion so meshes are in their
        # final directories (hf_mesh/, ti_surface_overlays/, etc.)
        self._organize_files(dirs)

        self._generate_central_surface(ti_path, dirs["ti_surfaces"])

        self.logger.info("NIfTI transformation: Started")
        transform_to_nifti(
            dirs["ti_mesh"], dirs["ti_niftis"], sid, self.m2m_dir, self.logger
        )
        transform_to_nifti(
            dirs["hf_mesh"],
            dirs["hf_niftis"],
            sid,
            self.m2m_dir,
            self.logger,
            fields=["magnE"],
        )
        self.logger.info("NIfTI transformation: \u2713 Complete")

        convert_t1_to_mni(self.m2m_dir, sid, self.logger)

        return ti_path

    def _calculate_ti_normal(
        self, hf_dir: str, output_dir: str, montage_name: str
    ) -> None:
        """Compute TI_normal on the cortical surface (requires surface overlays from SimNIBS)."""
        sid = self.config.subject_id
        cond = self.config.conductivity
        overlays = os.path.join(hf_dir, "subject_overlays")
        c1 = os.path.join(overlays, f"{sid}_TDCS_1_{cond}_central.msh")
        c2 = os.path.join(overlays, f"{sid}_TDCS_2_{cond}_central.msh")

        cm1 = mesh_io.read_msh(c1)
        cm2 = mesh_io.read_msh(c2)

        if "E" in cm1.field:
            ef1_v = cm1.field["E"].value
            ef2_v = cm2.field["E"].value
        else:
            normals = cm1.nodes_normals().value
            ef1_v = cm1.field["E_normal"].value.reshape(-1, 1) * normals
            ef2_v = cm2.field["E_normal"].value.reshape(-1, 1) * normals

        TI_normal = TI.get_dirTI(ef1_v, ef2_v, cm1.nodes_normals().value)

        mout = deepcopy(cm1)
        mout.nodedata = []
        mout.add_node_field(TI_normal, "TI_normal")

        normal_path = os.path.join(output_dir, f"{montage_name}_normal.msh")
        mesh_io.write_msh(mout, normal_path)
        mout.view(visible_fields=["TI_normal"]).write_opt(normal_path)
        self.logger.debug(f"TI_normal saved: {normal_path}")

    def _organize_files(self, dirs: dict) -> None:
        """Move SimNIBS output files into the BIDS directory structure."""
        hf = dirs["hf_dir"]

        # Move HF mesh files (.msh, .geo, .opt) into hf_mesh/
        cond = self.config.conductivity
        for pattern in ("TDCS_1", "TDCS_2"):
            for ext in (".geo", f"{cond}.msh", f"{cond}.msh.opt"):
                for f in glob.glob(os.path.join(hf, f"*{pattern}*{ext}")):
                    safe_move(
                        f,
                        os.path.join(dirs["hf_mesh"], os.path.basename(f)),
                    )

        # Move surface overlays (needed for TI_normal)
        overlays = os.path.join(hf, "subject_overlays")
        if os.path.isdir(overlays):
            for fname in os.listdir(overlays):
                safe_move(
                    os.path.join(overlays, fname),
                    os.path.join(dirs["ti_surface_overlays"], fname),
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
