#!/usr/bin/env simnibs_python
"""
N-pair Multi-channel Temporal Interference (mTI) simulation.

Supports arbitrary even numbers of electrode pairs (4, 6, 8, ...):
  - Each pair produces one HF E-field via SimNIBS TDCS
  - Adjacent pairs are combined via binary-tree TI recursion
  - Intermediate TI vector fields are saved for inspection

Example with 4 pairs (A/B/C/D):
  - TI_AB = TI(E_A, E_B),  TI_CD = TI(E_C, E_D)
  - mTI   = TI(TI_AB, TI_CD)
"""

import glob
import os
import shutil
import string
from copy import deepcopy

import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

from tit import constants as const
from tit.calc import get_nTI_vectors, get_TI_vectors
from tit.paths import get_path_manager
from tit.sim.config import SimulationConfig, MontageConfig, SimulationMode
from tit.sim.utils import (
    convert_t1_to_mni,
    create_simulation_config_file,
    extract_fields,
    run_montage_visualization,
    safe_move,
    setup_montage_directories,
    transform_to_nifti,
)

# Brain tissue crop mask — ranges defined in constants.BRAIN_TISSUE_TAG_RANGES
_TAGS_KEEP = np.hstack([np.arange(lo, hi) for lo, hi in const.BRAIN_TISSUE_TAG_RANGES])


class mTISimulation:
    """
    Runs a single N-pair mTI simulation (N >= 4, even).

    Pipeline:
      1. Set up BIDS output directory structure
      2. Visualize electrode placement
      3. Build SimNIBS SESSION (N TDCS lists), run FEM
      4. Compute intermediate TI vector fields via binary-tree pairing
      5. Compute final mTI_max from the combined TI field
      6. Extract GM/WM, convert to NIfTI, organize outputs
    """

    def __init__(self, config: SimulationConfig, montage: MontageConfig, logger):
        self.config = config
        self.montage = montage
        self.logger = logger
        self.pm = get_path_manager()
        self.m2m_dir = self.pm.m2m(config.subject_id)

    def run(self, simulation_dir: str) -> dict:
        """Execute the full pipeline. Returns a result dict."""
        montage_dir = self.pm.simulation(
            self.config.subject_id,
            self.montage.name,
        )
        dirs = setup_montage_directories(montage_dir, SimulationMode.MTI)
        create_simulation_config_file(
            self.config, self.montage, dirs["documentation"], self.logger
        )

        viz_pairs = None if self.montage.is_xyz else self.montage.electrode_pairs

        run_montage_visualization(
            montage_name=self.montage.name,
            simulation_mode=SimulationMode.MTI,
            eeg_net=self.montage.eeg_net,
            output_dir=dirs["mti_montage_imgs"],
            project_dir=self.config.project_dir,
            logger=self.logger,
            electrode_pairs=viz_pairs,
        )

        self.logger.info("SimNIBS simulation: Started")
        run_simnibs(self._build_session(dirs["hf_dir"]))
        self.logger.info("SimNIBS simulation: ✓ Complete")

        output_mesh = self._post_process(dirs)
        self.logger.info(f"✓ {self.montage.name} complete")

        return {
            "montage_name": self.montage.name,
            "montage_type": "mTI",
            "status": "completed",
            "output_mesh": output_mesh,
        }

    # ── Session building ────────────────────────────────────────────────────────────────

    def _build_session(self, output_dir: str) -> sim_struct.SESSION:
        """Build SimNIBS SESSION for N-pair mTI."""
        cfg = self.config
        n_pairs = self.montage.num_pairs
        S = sim_struct.SESSION()
        S.subpath = self.m2m_dir
        S.fnamehead = os.path.join(self.m2m_dir, f"{cfg.subject_id}.msh")
        S.pathfem = output_dir
        S.map_to_surf = cfg.map_to_surf
        S.map_to_vol = cfg.map_to_vol
        S.map_to_MNI = cfg.map_to_mni
        S.map_to_fsavg = cfg.map_to_fsavg
        S.open_in_gmsh = cfg.open_in_gmsh
        S.tissues_in_niftis = cfg.tissues_in_niftis

        if not self.montage.is_xyz:
            eeg_net = self.montage.eeg_net
            S.eeg_cap = os.path.join(self.pm.eeg_positions(cfg.subject_id), eeg_net)

        tensor = os.path.join(self.m2m_dir, "DTI_coregT1_tensor.nii.gz")
        if os.path.exists(tensor):
            S.fname_tensor = tensor

        for i in range(n_pairs):
            current = cfg.intensities.values[i] / 1000.0
            tdcs = S.add_tdcslist()
            tdcs.anisotropy_type = cfg.conductivity_type.value
            tdcs.aniso_maxratio = cfg.aniso_maxratio
            tdcs.aniso_maxcond = cfg.aniso_maxcond
            tdcs.currents = [current, -current]
            self._apply_tissue_conductivities(tdcs)
            for idx, pos in enumerate(self.montage.electrode_pairs[i]):
                el = tdcs.add_electrode()
                el.channelnr = idx + 1
                el.centre = pos
                self._configure_electrode(el)

        return S

    def _configure_electrode(self, electrode) -> None:
        el_cfg = self.config.electrode
        electrode.shape = el_cfg.shape
        electrode.dimensions = el_cfg.dimensions
        electrode.thickness = [el_cfg.thickness, el_cfg.sponge_thickness]

    def _apply_tissue_conductivities(self, tdcs) -> None:
        for i in range(len(tdcs.cond)):
            env_var = f"TISSUE_COND_{i + 1}"
            if env_var in os.environ:
                tdcs.cond[i].value = float(os.environ[env_var])

    # ── Post-processing ────────────────────────────────────────────────────────────────

    def _post_process(self, dirs: dict) -> str:
        sid = self.config.subject_id
        cond = self.config.conductivity_type.value
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

        # Final mTI using recursive binary-tree combination
        mti_vectors = get_nTI_vectors(e_fields)
        mti_field = np.linalg.norm(mti_vectors, axis=1)
        mout = deepcopy(meshes[0])
        mout.elmdata = []
        mout.add_element_field(mti_field, "TI_Max")

        mti_path = os.path.join(dirs["mti_mesh"], f"{name}_mTI.msh")
        mesh_io.write_msh(mout, mti_path)
        mout.view(visible_tags=[1002, 1006], visible_fields="TI_Max").write_opt(
            mti_path
        )
        self.logger.info(f"mTI_max saved: {mti_path}")

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
        self.logger.info("Field extraction: ✓ Complete")

        self.logger.info("NIfTI transformation: Started")
        transform_to_nifti(
            dirs["mti_mesh"], dirs["mti_niftis"], sid, self.m2m_dir, self.logger
        )
        self.logger.info("NIfTI transformation: ✓ Complete")

        self._organize_files(dirs)
        convert_t1_to_mni(self.m2m_dir, sid, self.logger)

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
        """Move HF files, renaming pairs 1..N → A..Z for mTI convention."""
        hf = dirs["hf_dir"]
        n_pairs = self.montage.num_pairs
        letters = string.ascii_uppercase

        for i in range(1, n_pairs + 1):
            ltr = letters[i - 1]
            for ext in (".geo", "scalar.msh", "scalar.msh.opt"):
                for f in glob.glob(os.path.join(hf, f"*TDCS_{i}*{ext}")):
                    new_name = os.path.basename(f).replace(f"TDCS_{i}", f"TDCS_{ltr}")
                    safe_move(f, os.path.join(dirs["hf_mesh"], new_name))

        # subject_volumes not needed for mTI (recursive removal intentional)
        shutil.rmtree(os.path.join(hf, "subject_volumes"))

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
