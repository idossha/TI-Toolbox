#!/usr/bin/env simnibs_python
"""N-channel Multi-channel Temporal Interference (mTI) simulation.

Implements :class:`mTISimulation`, the concrete ``BaseSimulation`` subclass
for multi-channel TI stimulation with an arbitrary even number of channels
(4, 6, 8, ...):

* Each channel produces one HF E-field via SimNIBS TDCS.
* The mTI envelope is the joint envelope maximum
  (:func:`tit.calc.envelope_max`) over all N channel fields
  jointly -- *not* a recursive TI-of-TI combination of per-pair envelopes
  (that approximation is physically invalid).
* Channels are paired positionally: each two consecutive channels form a
  beating pair at a common difference frequency (channels 1 and 2 the first
  pair, 3 and 4 the second, and so on; on disk the channels are lettered
  ``A``, ``B``, ``C``, ``D`` ...).

Example with 4 channels (on disk A/B/C/D)::

    mTI = envelope_max([E_A, E_B, E_C, E_D])

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

from simnibs import sim_struct

from tit import constants as const
from tit.sim.base import BaseSimulation
from tit.sim.config import SimulationMode
from tit.sim.utils import safe_move


class mTISimulation(BaseSimulation):
    """Run a single N-channel mTI simulation (N >= 4, even).

    Pipeline
    --------
    1. Set up BIDS output directory structure.
    2. Visualize electrode placement.
    3. Build SimNIBS SESSION (N TDCS lists), run FEM.
    4. Compute ``mTI_max`` from the modulation-depth envelope over all N
       channel fields jointly, plus its orientation-averaged companion
       ``TI_avg`` and the ``hf_peak``/``hf_rms``/``hf_power_density``
       kHz-exposure maps (always over all N fields), and the central surface
       with them and ``TI_normal``.
    5. Organize outputs; with ``map_to_vol``, write one NIfTI per field (whole,
       grey and white matter).

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
        """Write the mTI field mesh and its central surface; NIfTIs only with ``map_to_vol``.

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
        name = self.montage.name
        n_pairs = self.montage.num_pairs
        if n_pairs > 26:
            raise ValueError(
                f"mTI supports at most 26 pairs (A-Z labeling), got {n_pairs}"
            )
        meshes = self._cropped_carriers(dirs["hf_dir"], n_pairs)
        # The envelope of all N channel fields jointly -- not a recursive TI-of-TI.
        mti_path = os.path.join(dirs["mti_mesh"], f"{name}_mTI.msh")
        volume = self._write_volume_mesh(meshes, const.FIELD_MTI_MAX, mti_path)
        self._write_central_surface(
            volume,
            meshes,
            os.path.join(dirs["mti_surfaces"], f"{name}_mTI_central.msh"),
        )
        del meshes, volume  # free the channel meshes before the NIfTI pool forks
        self._organize_files(dirs)
        if self.config.map_to_vol:
            self._write_niftis(dirs, mti_path, "mti_niftis")
        return mti_path

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
