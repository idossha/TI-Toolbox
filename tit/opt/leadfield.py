"""Leadfield matrix generator for TI optimization.

Integrates with SimNIBS to create leadfield matrices via
``TDCSLEADFIELD``.  The leadfield encodes each electrode's
contribution to the electric field at every mesh element, enabling
fast objective-function evaluation during optimization without
re-running the full FEM solver.

Public API
----------
LeadfieldGenerator
    Object-oriented interface for leadfield generation, listing, and
    electrode-name extraction.

See Also
--------
tit.opt.flex.flex.run_flex_search : Uses the leadfield indirectly via SimNIBS.
tit.opt.ex.engine.ExSearchEngine : Loads the leadfield for exhaustive search.
"""

import glob
import logging
import os
import shutil
from pathlib import Path
from typing import Callable

from tit.paths import get_path_manager

log = logging.getLogger(__name__)


class LeadfieldGenerator:
    """Generate and list leadfield matrices for TI optimization.

    Wraps SimNIBS ``TDCSLEADFIELD`` to produce HDF5 leadfield files
    that the exhaustive-search and flex-search pipelines consume.

    Parameters
    ----------
    subject_id : str
        Subject identifier (e.g. ``"101"``).
    electrode_cap : str
        EEG cap name without ``.csv`` (e.g. ``"GSN-HydroCel-185"``).
    progress_callback : callable or None
        Optional ``callback(message, level)`` for GUI progress updates.
    termination_flag : callable or None
        Optional callable returning ``True`` when the user cancels.

    See Also
    --------
    tit.opt.ex.engine.ExSearchEngine : Consumes the generated leadfield.
    """

    def __init__(
        self,
        subject_id: str,
        electrode_cap: str = "EEG10-10",
        progress_callback: Callable | None = None,
        termination_flag: Callable[[], bool] | None = None,
    ) -> None:
        self.subject_id = subject_id
        self.electrode_cap = electrode_cap
        self._progress_callback = progress_callback
        self._termination_flag = termination_flag
        self.pm = get_path_manager()

    def _log(self, message: str, level: str = "info") -> None:
        """Emit a log message, forwarding to the progress callback if set."""
        if self._progress_callback:
            self._progress_callback(message, level)
        getattr(log, level, log.info)(message)

    def _cleanup(self, *dirs: Path) -> None:
        """Remove stale SimNIBS artefacts from *dirs*."""
        m2m_dir = Path(self.pm.m2m(self.subject_id))
        for directory in dirs:
            for f in glob.glob(str(directory / "simnibs_simulation*.mat")):
                os.remove(f)
            for f in glob.glob(str(directory / "*_electrodes_*.msh")):
                os.remove(f)
        shutil.rmtree(m2m_dir / "leadfield", ignore_errors=True)
        (m2m_dir / f"{self.subject_id}_ROI.msh").unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        output_dir: str | Path | None = None,
        tissues: list[int] | None = None,
        cleanup: bool = True,
    ) -> Path:
        """Generate a leadfield matrix via SimNIBS.

        Parameters
        ----------
        output_dir : str or Path or None
            Output directory.  Defaults to
            ``pm.leadfields(subject_id)``.
        tissues : list of int or None
            Tissue tags (1 = WM, 2 = GM).  Default: ``[1, 2]``.
        cleanup : bool
            Remove stale SimNIBS artefacts before running.

        Returns
        -------
        Path
            Path to the generated HDF5 leadfield file.

        Raises
        ------
        InterruptedError
            If cancelled via *termination_flag*.
        """
        from simnibs import sim_struct
        import simnibs

        tissues = [1, 2]
        m2m_dir = Path(self.pm.m2m(self.subject_id))
        output_dir = Path(
            output_dir or self.pm.ensure(self.pm.leadfields(self.subject_id))
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        self._cleanup(output_dir, m2m_dir)

        tdcs_lf = sim_struct.TDCSLEADFIELD()
        tdcs_lf.fnamehead = str(m2m_dir / f"{self.subject_id}.msh")
        tdcs_lf.subpath = str(m2m_dir)
        tdcs_lf.pathfem = str(output_dir)
        tdcs_lf.interpolation = None
        tdcs_lf.map_to_surf = False
        tdcs_lf.tissues = tissues
        tdcs_lf.eeg_cap = str(
            Path(self.pm.eeg_positions(self.subject_id)) / f"{self.electrode_cap}.csv"
        )

        if self._termination_flag and self._termination_flag():
            raise InterruptedError("Leadfield generation cancelled before starting")

        self._log(
            f"Generating leadfield for {self.subject_id} (cap={self.electrode_cap})"
        )
        simnibs.run_simnibs(tdcs_lf)

        if self._termination_flag and self._termination_flag():
            raise InterruptedError("Leadfield generation cancelled after SimNIBS")

        hdf5_path = next(output_dir.glob("*.hdf5"))
        self._log(f"Leadfield ready: {hdf5_path}")
        return hdf5_path

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_leadfields(
        self, subject_id: str | None = None
    ) -> list[tuple[str, str, float]]:
        """List available leadfield HDF5 files for a subject.

        Parameters
        ----------
        subject_id : str or None
            Subject ID.  Defaults to ``self.subject_id``.

        Returns
        -------
        list of tuple[str, str, float]
            Sorted list of ``(net_name, hdf5_path, size_gb)`` tuples.
        """
        sid = subject_id or self.subject_id
        leadfields_dir = Path(self.pm.leadfields(sid))

        out: list[tuple[str, str, float]] = []
        for item in leadfields_dir.iterdir():
            if item.suffix != ".hdf5":
                continue

            stem = item.stem
            if "_leadfield_" in stem:
                net_name = stem.split("_leadfield_", 1)[-1]
            elif stem.endswith("_leadfield"):
                net_name = stem[: -len("_leadfield")]
            else:
                net_name = stem

            for prefix in (f"{sid}_", sid):
                if net_name.startswith(prefix):
                    net_name = net_name[len(prefix) :]
                    break

            net_name = net_name.strip("_") or "unknown"
            out.append((net_name, str(item), item.stat().st_size / (1024**3)))

        return sorted(out)

    def get_electrode_names(self, cap_name: str | None = None) -> list[str]:
        """Extract electrode labels from an EEG cap via SimNIBS.

        Parameters
        ----------
        cap_name : str or None
            EEG cap name (without ``.csv``).  Defaults to
            ``self.electrode_cap``.

        Returns
        -------
        list of str
            Sorted list of electrode label strings.
        """
        from simnibs.utils.csv_reader import eeg_positions

        cap_name = cap_name or self.electrode_cap
        eeg_pos = eeg_positions(str(self.pm.m2m(self.subject_id)), cap_name=cap_name)
        return sorted(eeg_pos.keys())
