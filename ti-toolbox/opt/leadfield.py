"""
Leadfield matrix generator for optimization and other applications
Integrates with SimNIBS to create leadfield matrices
"""

import os
import sys
import shutil
import h5py
from pathlib import Path

# Add utils to path for logging
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from tools import logging_util
from core import get_path_manager


class LeadfieldGenerator:
    """Generate and load leadfield matrices for TI optimization
    
    This class provides a unified interface for leadfield generation and management,
    supporting both HDF5 and NPY formats with consistent naming conventions.
    """

    def __init__(self, subject_dir, electrode_cap='EEG10-10', progress_callback=None, termination_flag=None):
        """
        Initialize leadfield generator

        Args:
            subject_dir: Path to subject directory (m2m folder) or subject_id
            electrode_cap: Electrode cap type (e.g., 'EEG10-10', 'GSN-256')
            progress_callback: Optional callback function(message, type) for progress updates
            termination_flag: Optional callable that returns True if generation should be terminated
        """
        self.subject_dir = Path(subject_dir)
        self.electrode_cap = electrode_cap
        self._progress_callback = progress_callback
        self._termination_flag = termination_flag
        self._simnibs_process = None
        
        # Initialize PathManager
        self.pm = get_path_manager()
        
        # Extract subject_id from subject_dir path
        self.subject_id = self.subject_dir.name.replace('m2m_', '')

        # Setup logger
        if progress_callback is None:
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
        """Clean up old SimNIBS simulation files, temporary directories, and ROI mesh files."""
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

        # Remove ROI mesh file
        subject_id = self.subject_dir.name.replace('m2m_', '')
        roi_file = self.subject_dir / f"{subject_id}_ROI.msh"
        if roi_file.exists():
            self._log("  Removing old ROI mesh file...", 'info')
            try:
                os.remove(roi_file)
                self._log(f"  Removed: {roi_file.name}", 'info')
            except Exception as e:
                self._log(f"  Warning: Could not remove {roi_file.name}: {e}", 'warning')

    def _cleanup_output_dir(self, output_dir):
        """Clean up old simulation files in the output directory (preserves existing leadfields)."""
        import glob

        self._log("Checking for old simulation files in output directory...", 'info')

        # Remove old simulation .mat files in output directory
        old_sim_files = glob.glob(str(output_dir / "simnibs_simulation*.mat"))
        if old_sim_files:
            self._log(f"  Found {len(old_sim_files)} old simulation file(s) in output directory, cleaning up...", 'info')
            for sim_file in old_sim_files:
                try:
                    os.remove(sim_file)
                    self._log(f"  Removed: {os.path.basename(sim_file)}", 'info')
                except Exception as e:
                    self._log(f"  Warning: Could not remove {os.path.basename(sim_file)}: {e}", 'warning')

        # Remove old .msh files that SimNIBS creates (e.g., 101_electrodes_EEG10-20_Okamoto_2004.msh)
        # Note: Preserving existing leadfield HDF5 files
        old_msh_files = glob.glob(str(output_dir / "*_electrodes_*.msh"))
        if old_msh_files:
            self._log(f"  Found {len(old_msh_files)} old electrode mesh file(s) in output directory, cleaning up...", 'info')
            for msh_file in old_msh_files:
                try:
                    os.remove(msh_file)
                    self._log(f"  Removed: {os.path.basename(msh_file)}", 'info')
                except Exception as e:
                    self._log(f"  Warning: Could not remove {os.path.basename(msh_file)}: {e}", 'warning')

    def generate_leadfield(self, output_dir=None, tissues=[1, 2], eeg_cap_path=None, cleanup=True):
        """
        Generate leadfield matrix using SimNIBS

        Args:
            output_dir: Output directory for leadfield (default: subject_dir)
            tissues: Tissue types to include [1=GM, 2=WM]
            eeg_cap_path: Path to EEG cap CSV file (optional, will look in eeg_positions if not provided)
            cleanup: Whether to clean up old simulation files before running (default: True)

        Returns:
            dict: Dictionary with path {'hdf5': hdf5_path}
        """
        from simnibs import sim_struct
        import simnibs

        if output_dir is None:
            # Use PathManager to get leadfield directory
            output_dir = self.pm.get_leadfield_dir(self.subject_id)
            if output_dir is None:
                # Fallback to manual construction if PathManager doesn't find it
                output_dir = self.subject_dir.parent / "leadfields"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Clean up old simulation files in output directory
        if cleanup:
            self._cleanup_output_dir(output_dir)

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
            # Try to find in eeg_positions directory using PathManager
            eeg_positions_dir = self.pm.get_eeg_positions_dir(self.subject_id)
            if eeg_positions_dir and os.path.exists(eeg_positions_dir):
                cap_file = Path(eeg_positions_dir) / f"{self.electrode_cap}.csv"
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
        self._log("Setting up SimNIBS leadfield calculation...", 'info')

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

        if self._progress_callback:
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

        self._log("SimNIBS leadfield computation completed", 'info')

        # Find generated HDF5 file
        self._log("Processing generated leadfield files...", 'info')
        hdf5_files = list(output_dir.glob('*.hdf5'))
        if not hdf5_files:
            raise FileNotFoundError(f"No HDF5 leadfield file found in {output_dir}")

        hdf5_path = hdf5_files[0]

        # Use the filename that SimNIBS generated (simplified naming - no renaming)
        self._log(f"Leadfield generated: {hdf5_path}", 'success')

        result = {'hdf5': str(hdf5_path)}

        return result

    def list_available_leadfields(self, subject_id=None):
        """
        List available leadfield HDF5 files for a subject.

        Args:
            subject_id: Subject ID (optional, will use self.subject_id if not provided)

        Returns:
            list: List of tuples (net_name, hdf5_path, file_size_gb)
        """
        if subject_id is None:
            subject_id = self.subject_id

        # Use PathManager to get leadfield directory
        leadfields_dir = self.pm.get_leadfield_dir(subject_id)
        
        leadfields = []
        if leadfields_dir and os.path.exists(leadfields_dir):
            leadfields_dir = Path(leadfields_dir)
            for item in leadfields_dir.iterdir():
                # Look for files matching pattern: {net_name}_leadfield.hdf5
                if item.is_file() and item.name.endswith("_leadfield.hdf5"):
                    hdf5_file = item
                    if hdf5_file.exists():
                        # Extract net name from filename pattern: {net_name}_leadfield.hdf5
                        net_name = item.name.replace("_leadfield.hdf5", "")
                        # Get file size in GB
                        try:
                            file_size = hdf5_file.stat().st_size / (1024**3)  # GB
                        except OSError:
                            file_size = 0.0
                        leadfields.append((net_name, str(hdf5_file), file_size))

        return sorted(leadfields, key=lambda x: x[0])

    def list_available_leadfields_hdf5(self, subject_id=None):
        """
        List available leadfield HDF5 files for a subject.

        Args:
            subject_id: Subject ID (optional, will use self.subject_id if not provided)

        Returns:
            list: List of tuples (net_name, hdf5_path, file_size_gb)
        """
        if subject_id is None:
            subject_id = self.subject_id

        # Use PathManager to get leadfield directory
        leadfields_dir = self.pm.get_leadfield_dir(subject_id)

        leadfields = []
        if leadfields_dir and os.path.exists(leadfields_dir):
            leadfields_dir = Path(leadfields_dir)
            for item in leadfields_dir.iterdir():
                # Look for HDF5 files that contain "leadfield" in the name (flexible naming)
                if item.is_file() and item.name.endswith(".hdf5") and "leadfield" in item.name.lower():
                    hdf5_file = item
                    if hdf5_file.exists():
                        # Extract net name more flexibly - try different SimNIBS naming patterns
                        filename = item.name

                        # Try to extract net_name from various SimNIBS naming patterns
                        if "_leadfield_" in filename:
                            # Split by "_leadfield_" and take the part after it, remove .hdf5
                            parts = filename.split("_leadfield_")
                            if len(parts) == 2:
                                net_name = parts[1].replace(".hdf5", "")
                            else:
                                net_name = filename.replace("_leadfield_", "").replace(".hdf5", "")
                        elif filename.endswith("_leadfield.hdf5"):
                            # Standard pattern: {net_name}_leadfield.hdf5
                            net_name = filename.replace("_leadfield.hdf5", "")
                        else:
                            # Fallback: remove .hdf5 and try to clean up
                            net_name = filename.replace(".hdf5", "")

                        # Clean up the net_name (remove subject_id prefix if present)
                        if net_name.startswith(f"{subject_id}_"):
                            net_name = net_name.replace(f"{subject_id}_", "", 1)
                        elif net_name.startswith(f"{subject_id}"):
                            net_name = net_name.replace(f"{subject_id}", "", 1)

                        # Clean up extra underscores and empty parts
                        net_name = net_name.strip("_")
                        if not net_name:
                            net_name = "unknown"

                        # Get file size in GB
                        try:
                            file_size = hdf5_file.stat().st_size / (1024**3)  # GB
                        except OSError:
                            file_size = 0.0
                        leadfields.append((net_name, str(hdf5_file), file_size))

        return sorted(leadfields, key=lambda x: x[0])


    def get_electrode_names_from_cap(self, eeg_cap_path=None, cap_name=None):
        """
        Extract electrode names from an EEG cap CSV file.

        Args:
            eeg_cap_path: Path to EEG cap CSV file (optional)
            cap_name: Name of EEG cap (will look in subject_dir/eeg_positions/)

        Returns:
            list: List of electrode names
        """
        if eeg_cap_path is None and cap_name is None:
            cap_name = self.electrode_cap

        if eeg_cap_path is None:
            if cap_name is None:
                raise ValueError("Either eeg_cap_path or cap_name must be provided")
            
            # Try to find matching cap file
            eeg_cap_path = self._find_eeg_cap_file(cap_name)
            if eeg_cap_path is None:
                raise FileNotFoundError(f"EEG cap file not found for: {cap_name}")

        eeg_cap_path = Path(eeg_cap_path)
        if not eeg_cap_path.exists():
            raise FileNotFoundError(f"EEG cap file not found: {eeg_cap_path}")

        electrodes = []
        with open(eeg_cap_path, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 4 and parts[0] not in ['Label', 'Electrode', '']:  # Skip header and empty lines
                    electrode_label = parts[0].strip()  # First column is the label
                    if electrode_label and not electrode_label.replace('.', '').replace('-', '').isdigit():  # Skip numeric values
                        electrodes.append(electrode_label)

        return sorted(electrodes)

    def _find_eeg_cap_file(self, cap_name):
        """
        Find EEG cap file with flexible name matching using PathManager.
        
        Args:
            cap_name: Name of the cap to find
            
        Returns:
            Path to the found cap file or None
        """
        # Look in subject's eeg_positions directory first using PathManager
        eeg_positions_dir = self.pm.get_eeg_positions_dir(self.subject_id)
        
        if eeg_positions_dir and os.path.exists(eeg_positions_dir):
            eeg_positions_dir = Path(eeg_positions_dir)
            
            # Try exact match first
            exact_match = eeg_positions_dir / f"{cap_name}.csv"
            if exact_match.exists():
                return exact_match
        
        return None

 
if __name__ == '__main__':
    """
    Command line interface for leadfield generation.
    Usage: python leadfield.py <m2m_dir> <eeg_cap_path> <net_name>
    """
    import sys

    if len(sys.argv) != 4:
        print("Usage: python leadfield.py <m2m_dir> <eeg_cap_path> <net_name>")
        sys.exit(1)

    m2m_dir = sys.argv[1]
    eeg_cap_path = sys.argv[2]
    net_name = sys.argv[3]

    # Create output directory: project_dir/derivatives/SimNIBS/sub-{subject_id}/leadfields/
    from pathlib import Path
    m2m_path = Path(m2m_dir)
    # Go up to subject directory, then down to leadfields
    leadfield_dir = m2m_path.parent / "leadfields"

    print(f"Creating leadfield in: {leadfield_dir}")

    # Create leadfield generator
    gen = LeadfieldGenerator(m2m_dir, electrode_cap=net_name)

    try:
        # Generate leadfield (creates HDF5 file)
        hdf5_path = gen.generate_leadfield(
            output_dir=str(leadfield_dir),
            tissues=[1, 2],  # GM and WM
            eeg_cap_path=eeg_cap_path
        )

        print(f"Leadfield created successfully: {hdf5_path}")

    except Exception as e:
        print(f"Error creating leadfield: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

