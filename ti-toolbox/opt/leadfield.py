"""
Leadfield matrix generator for MOVEA optimization and other applications
Integrates with SimNIBS to create leadfield matrices
"""

import os
import sys
import shutil
import numpy as np
import h5py
from pathlib import Path

# Add utils to path for logging
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from tools import logging_util
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False


class LeadfieldGenerator:
    """Generate and load leadfield matrices for MOVEA optimization"""

    def __init__(self, subject_dir, electrode_cap='EEG10-10', progress_callback=None, termination_flag=None):
        """
        Initialize leadfield generator

        Args:
            subject_dir: Path to subject directory (m2m folder)
            electrode_cap: Electrode cap type (e.g., 'EEG10-10', 'GSN-256')
            progress_callback: Optional callback function(message, type) for progress updates
            termination_flag: Optional callable that returns True if generation should be terminated
        """
        self.subject_dir = Path(subject_dir)
        self.electrode_cap = electrode_cap
        self.lfm = None
        self.positions = None
        self.electrode_names = None
        self._progress_callback = progress_callback
        self._termination_flag = termination_flag
        self._simnibs_process = None

        # Setup logger if available
        if LOGGER_AVAILABLE and progress_callback is None:
            log_file = os.path.join(os.path.expanduser("~"), ".ti_toolbox", "logs", "leadfield_generator.log")
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            self.logger = logging_util.get_logger("LeadfieldGenerator", log_file, overwrite=False)
            logging_util.configure_external_loggers(['simnibs', 'mesh_io'], self.logger)
        else:
            self.logger = None

    def _log(self, message, msg_type='info'):
        """Send log message through callback or logger"""
        if self._progress_callback:
            self._progress_callback(message, msg_type)
        elif self.logger:
            if msg_type == 'error':
                self.logger.error(message)
            elif msg_type == 'warning':
                self.logger.warning(message)
            elif msg_type == 'debug':
                self.logger.debug(message)
            else:
                self.logger.info(message)
        else:
            print(message)

    def cleanup_old_simulations(self):
        """Clean up old SimNIBS simulation files and temporary directories."""
        import glob
        import shutil

        self._log("Checking for old simulation files...", 'info')

        # Remove old simulation .mat files
        old_sim_files = glob.glob(str(self.subject_dir / "simnibs_simulation*.mat"))
        if old_sim_files:
            self._log(f"  Found {len(old_sim_files)} old simulation file(s), cleaning up...", 'info')
            for sim_file in old_sim_files:
                try:
                    os.remove(sim_file)
                    self._log(f"  Removed: {os.path.basename(sim_file)}", 'info')
                except Exception as e:
                    self._log(f"  Warning: Could not remove {os.path.basename(sim_file)}: {e}", 'warning')

        # Remove temporary leadfield directory
        temp_leadfield_dir = self.subject_dir / 'leadfield'
        if temp_leadfield_dir.exists():
            self._log("  Removing old temporary leadfield directory...", 'info')
            try:
                shutil.rmtree(temp_leadfield_dir)
                self._log("  Removed: leadfield/", 'info')
            except Exception as e:
                self._log(f"  Warning: Could not remove leadfield directory: {e}", 'warning')

    def generate_leadfield(self, output_dir=None, tissues=[1, 2], eeg_cap_path=None, cleanup=True):
        """
        Generate leadfield matrix using SimNIBS

        Args:
            output_dir: Output directory for leadfield (default: subject_dir)
            tissues: Tissue types to include [1=GM, 2=WM]
            eeg_cap_path: Path to EEG cap CSV file (optional, will look in eeg_positions if not provided)
            cleanup: Whether to clean up old simulation files before running (default: True)

        Returns:
            Path to generated HDF5 file
        """
        from simnibs import sim_struct
        import simnibs

        if output_dir is None:
            output_dir = self.subject_dir / 'leadfield'
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Setup SimNIBS leadfield calculation
        tdcs_lf = sim_struct.TDCSLEADFIELD()

        # Find mesh file - try multiple naming conventions
        # Common patterns: {subject_id}.msh, m2m_{subject_id}.msh, {subject_dir_name}.msh
        subject_id = self.subject_dir.name.replace('m2m_', '')  # Extract subject ID

        possible_mesh_names = [
            f"{subject_id}.msh",  # Most common: 101.msh
            f"{self.subject_dir.name}.msh",  # m2m_101.msh
            "final.msh",  # Sometimes used
        ]

        mesh_file = None
        for mesh_name in possible_mesh_names:
            candidate = self.subject_dir / mesh_name
            if candidate.exists():
                mesh_file = candidate
                self._log(f"Found mesh file: {mesh_file}", 'info')
                break

        if mesh_file is None:
            # List available .msh files to help debug
            msh_files = list(self.subject_dir.glob("*.msh"))
            error_msg = f"Mesh file not found in {self.subject_dir}\n"
            error_msg += f"Tried: {', '.join(possible_mesh_names)}\n"
            if msh_files:
                error_msg += f"Available .msh files: {', '.join([f.name for f in msh_files])}"
            else:
                error_msg += "No .msh files found in directory"
            raise FileNotFoundError(error_msg)

        tdcs_lf.fnamehead = str(mesh_file)
        tdcs_lf.subpath = str(self.subject_dir)
        tdcs_lf.pathfem = str(output_dir)
        tdcs_lf.interpolation = None
        tdcs_lf.map_to_surf = False
        tdcs_lf.tissues = tissues

        # Set EEG cap path if provided
        if eeg_cap_path:
            if not Path(eeg_cap_path).exists():
                raise FileNotFoundError(f"EEG cap file not found: {eeg_cap_path}")
            tdcs_lf.eeg_cap = str(eeg_cap_path)
            self._log(f"Using EEG cap: {Path(eeg_cap_path).name}", 'info')
        elif self.electrode_cap and self.electrode_cap != 'EEG10-10':
            # Try to find in eeg_positions directory
            eeg_positions_dir = self.subject_dir / 'eeg_positions'
            if eeg_positions_dir.exists():
                cap_file = eeg_positions_dir / f"{self.electrode_cap}.csv"
                if cap_file.exists():
                    tdcs_lf.eeg_cap = str(cap_file)
                    self._log(f"Found EEG cap: {cap_file.name}", 'info')

        # Clean up old files if requested
        if cleanup:
            self.cleanup_old_simulations()

        self._log(f"Generating leadfield matrix for {self.subject_dir.name}...", 'info')
        self._log(f"Electrode cap: {self.electrode_cap if self.electrode_cap else 'Default'}", 'info')
        self._log(f"Tissues: {tissues} (1=GM, 2=WM)", 'info')
        self._log(f"Mesh file: {mesh_file.name}", 'info')

        # Redirect SimNIBS output to GUI console via callback (not terminal)
        import sys
        from io import StringIO
        import logging

        # Suppress SimNIBS console output by redirecting stdout/stderr to StringIO
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        # Configure SimNIBS logger to use callback if available
        simnibs_logger = logging.getLogger('simnibs')
        old_simnibs_handlers = simnibs_logger.handlers[:]

        if self._progress_callback and LOGGER_AVAILABLE:
            # Remove console handlers from SimNIBS logger
            logging_util.suppress_console_output(simnibs_logger)

            # Add callback handler to redirect to GUI
            logging_util.add_callback_handler(simnibs_logger, self._progress_callback, logging.INFO)

        # Run SimNIBS with termination checks
        simnibs_error = None
        try:
            # Check for termination before starting
            if self._termination_flag and self._termination_flag():
                self._log("Leadfield generation cancelled before starting", 'warning')
                raise InterruptedError("Leadfield generation was cancelled before starting")

            # Note: SimNIBS runs MPI processes that cannot be interrupted mid-execution
            # The termination check will take effect after SimNIBS completes
            self._log("Running SimNIBS (this cannot be interrupted mid-execution)...", 'info')
            simnibs.run_simnibs(tdcs_lf)

            # Check for termination after SimNIBS finishes
            if self._termination_flag and self._termination_flag():
                self._log("Leadfield generation cancelled after SimNIBS execution", 'warning')
                raise InterruptedError("Leadfield generation was cancelled")

        except Exception as e:
            simnibs_error = e
        finally:
            # Restore stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            # Restore SimNIBS logger handlers
            if self._progress_callback:
                simnibs_logger.handlers = old_simnibs_handlers

            # Send any captured stdout/stderr to callback (fallback for print statements)
            if self._progress_callback:
                stdout_text = stdout_capture.getvalue()
                stderr_text = stderr_capture.getvalue()
                if stdout_text.strip():
                    for line in stdout_text.strip().split('\n'):
                        if line.strip():
                            self._log(line, 'info')
                if stderr_text.strip():
                    for line in stderr_text.strip().split('\n'):
                        if line.strip():
                            self._log(line, 'warning')

        # Re-raise any error that occurred during SimNIBS run
        if simnibs_error:
            raise simnibs_error

        # Find generated HDF5 file
        hdf5_files = list(output_dir.glob('*.hdf5'))
        if not hdf5_files:
            raise FileNotFoundError(f"No HDF5 leadfield file found in {output_dir}")

        hdf5_path = hdf5_files[0]
        self._log(f"Leadfield generated: {hdf5_path}", 'success')

        return hdf5_path

    def load_from_hdf5(self, hdf5_path, compute_centroids=True):
        """
        Load leadfield matrix from SimNIBS HDF5 file

        Args:
            hdf5_path: Path to HDF5 leadfield file
            compute_centroids: If True, compute tetrahedral centroids for positions

        Returns:
            tuple: (leadfield_matrix, positions, electrode_names)
        """
        hdf5_path = Path(hdf5_path)
        if not hdf5_path.exists():
            raise FileNotFoundError(f"HDF5 file not found: {hdf5_path}")

        self._log(f"Loading leadfield from: {hdf5_path}", 'info')

        with h5py.File(hdf5_path, 'r') as f:
            # Load leadfield matrix
            self.lfm = np.array(f['mesh_leadfield']['leadfields']['tdcs_leadfield'])

            # Load node coordinates
            node_coords = np.array(f['mesh_leadfield']['nodes']['node_coord'])

            if compute_centroids:
                # Compute tetrahedral centroids (better for volume representation)
                index = np.array(f['mesh_leadfield']['elm']['node_number_list'])
                self.positions = np.zeros([self.lfm.shape[1], 3])
                for i in range(self.positions.shape[0]):
                    # Average of 4 tetrahedral vertices (indices are 1-based)
                    self.positions[i] = (
                        node_coords[index[i, 0] - 1] +
                        node_coords[index[i, 1] - 1] +
                        node_coords[index[i, 2] - 1] +
                        node_coords[index[i, 3] - 1]
                    ) / 4
            else:
                # Use node coordinates directly
                self.positions = node_coords[:self.lfm.shape[1]]

        self._log(f"Leadfield shape: {self.lfm.shape}", 'info')
        self._log(f"  Electrodes: {self.lfm.shape[0]}", 'info')
        self._log(f"  Voxels: {self.lfm.shape[1]}", 'info')
        self._log(f"  Components: {self.lfm.shape[2]} (x, y, z)", 'info')
        self._log(f"Position shape: {self.positions.shape}", 'info')

        return self.lfm, self.positions

    def save_numpy(self, output_dir):
        """
        Save leadfield and positions as numpy files

        Args:
            output_dir: Directory to save .npy files

        Returns:
            tuple: (lfm_path, pos_path)
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.lfm is None or self.positions is None:
            raise ValueError("Leadfield not loaded. Call load_from_hdf5 first.")

        lfm_path = output_dir / 'leadfield.npy'
        pos_path = output_dir / 'positions.npy'

        np.save(lfm_path, self.lfm)
        np.save(pos_path, self.positions)

        self._log(f"Saved leadfield to: {lfm_path}", 'success')
        self._log(f"Saved positions to: {pos_path}", 'success')

        return lfm_path, pos_path

    def load_numpy(self, lfm_path, pos_path):
        """
        Load leadfield and positions from numpy files

        Args:
            lfm_path: Path to leadfield .npy file
            pos_path: Path to positions .npy file

        Returns:
            tuple: (leadfield_matrix, positions)
        """
        lfm_path = Path(lfm_path)
        pos_path = Path(pos_path)

        if not lfm_path.exists():
            raise FileNotFoundError(f"Leadfield file not found: {lfm_path}")
        if not pos_path.exists():
            raise FileNotFoundError(f"Positions file not found: {pos_path}")

        self.lfm = np.load(lfm_path)
        self.positions = np.load(pos_path)

        self._log(f"Loaded leadfield: {self.lfm.shape}", 'info')
        self._log(f"Loaded positions: {self.positions.shape}", 'info')

        return self.lfm, self.positions

    def generate_and_save_numpy(self, output_dir, eeg_cap_file, cleanup_intermediate=True):
        """
        Complete workflow: Generate leadfield, convert to numpy, cleanup.

        Args:
            output_dir: Directory to save final .npy files
            eeg_cap_file: EEG cap filename (will look in subject_dir/eeg_positions/)
            cleanup_intermediate: Whether to remove intermediate HDF5 files (default: True)

        Returns:
            tuple: (lfm_path, pos_path, lfm_shape)
        """
        import shutil

        # Get EEG cap path
        eeg_cap_path = self.subject_dir / 'eeg_positions' / eeg_cap_file
        if not eeg_cap_path.exists():
            raise FileNotFoundError(f"EEG cap file not found: {eeg_cap_path}")

        # Generate leadfield to a temporary directory within output_dir (not in m2m_dir)
        self._log("", 'info')
        self._log("Generating leadfield with SimNIBS...", 'info')
        self._log("This may take 5-15 minutes depending on mesh size and electrode count", 'info')
        self._log("", 'info')

        # Convert output_dir to Path object for pathlib operations
        output_dir = Path(output_dir)

        # Create a temporary directory for intermediate SimNIBS files within output_dir
        temp_leadfield_dir = output_dir / '_temp_leadfield'
        temp_leadfield_dir.mkdir(parents=True, exist_ok=True)

        hdf5_file = self.generate_leadfield(
            output_dir=temp_leadfield_dir,
            tissues=[1, 2],
            eeg_cap_path=str(eeg_cap_path)
        )

        self._log(f"Leadfield generated: {Path(hdf5_file).name}", 'success')

        # Load and convert
        self._log("Loading and converting leadfield...", 'info')
        lfm, positions = self.load_from_hdf5(hdf5_file, compute_centroids=True)

        # Save as numpy files
        self._log("Saving numpy files...", 'info')
        output_dir.mkdir(parents=True, exist_ok=True)

        net_name = eeg_cap_file.replace('.csv', '')
        lfm_path = output_dir / f"{net_name}_leadfield.npy"
        pos_path = output_dir / f"{net_name}_positions.npy"

        np.save(lfm_path, lfm)
        np.save(pos_path, positions)

        # Move intermediate files to output directory (don't delete them)
        if cleanup_intermediate:
            self._log("Moving intermediate files to output directory...", 'info')
            try:
                if temp_leadfield_dir.exists():
                    # Move all files from temp directory to output directory
                    for file_path in temp_leadfield_dir.glob('*'):
                        if file_path.is_file():
                            destination = output_dir / file_path.name
                            shutil.move(str(file_path), str(destination))
                            self._log(f"  Moved: {file_path.name}", 'info')

                    # Remove the now-empty temporary directory
                    temp_leadfield_dir.rmdir()
                    self._log("  Removed empty temporary directory: _temp_leadfield/", 'info')
            except Exception as e:
                self._log(f"  Warning: File movement failed: {str(e)}", 'warning')

        return str(lfm_path), str(pos_path), lfm.shape


def convert_hdf5_to_numpy(hdf5_path, output_dir=None):
    """
    Convenience function to convert HDF5 leadfield to numpy files

    Args:
        hdf5_path: Path to HDF5 file
        output_dir: Output directory (default: same as HDF5)

    Returns:
        tuple: (lfm_path, pos_path)
    """
    if output_dir is None:
        output_dir = Path(hdf5_path).parent

    gen = LeadfieldGenerator(output_dir)
    gen.load_from_hdf5(hdf5_path)
    return gen.save_numpy(output_dir)

