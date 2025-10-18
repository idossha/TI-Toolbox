"""
Leadfield matrix generator for MOVEA optimization
Integrates with SimNIBS to create leadfield matrices
"""

import os
import numpy as np
import h5py
from pathlib import Path


class LeadfieldGenerator:
    """Generate and load leadfield matrices for MOVEA optimization"""
    
    def __init__(self, subject_dir, electrode_cap='EEG10-10'):
        """
        Initialize leadfield generator
        
        Args:
            subject_dir: Path to subject directory (m2m folder)
            electrode_cap: Electrode cap type (e.g., 'EEG10-10', 'GSN-256')
        """
        self.subject_dir = Path(subject_dir)
        self.electrode_cap = electrode_cap
        self.lfm = None
        self.positions = None
        self.electrode_names = None
    
    def generate_leadfield(self, output_dir=None, tissues=[1, 2], eeg_cap_path=None):
        """
        Generate leadfield matrix using SimNIBS
        
        Args:
            output_dir: Output directory for leadfield (default: subject_dir)
            tissues: Tissue types to include [1=GM, 2=WM]
            eeg_cap_path: Path to EEG cap CSV file (optional, will look in eeg_positions if not provided)
        
        Returns:
            Path to generated HDF5 file
        """
        try:
            from simnibs import sim_struct
            import simnibs
        except ImportError:
            raise ImportError("SimNIBS not found. Please install SimNIBS to generate leadfields.")
        
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
                print(f"Found mesh file: {mesh_file}")
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
            print(f"Using EEG cap: {Path(eeg_cap_path).name}")
        elif self.electrode_cap and self.electrode_cap != 'EEG10-10':
            # Try to find in eeg_positions directory
            eeg_positions_dir = self.subject_dir / 'eeg_positions'
            if eeg_positions_dir.exists():
                cap_file = eeg_positions_dir / f"{self.electrode_cap}.csv"
                if cap_file.exists():
                    tdcs_lf.eeg_cap = str(cap_file)
                    print(f"Found EEG cap: {cap_file.name}")
        
        print(f"Generating leadfield matrix for {self.subject_dir.name}...")
        print(f"Electrode cap: {self.electrode_cap if self.electrode_cap else 'Default'}")
        print(f"Tissues: {tissues} (1=GM, 2=WM)")
        print(f"Mesh file: {mesh_file.name}")
        
        simnibs.run_simnibs(tdcs_lf)
        
        # Find generated HDF5 file
        hdf5_files = list(output_dir.glob('*.hdf5'))
        if not hdf5_files:
            raise FileNotFoundError(f"No HDF5 leadfield file found in {output_dir}")
        
        hdf5_path = hdf5_files[0]
        print(f"Leadfield generated: {hdf5_path}")
        
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
        
        print(f"Loading leadfield from: {hdf5_path}")
        
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
        
        print(f"Leadfield shape: {self.lfm.shape}")
        print(f"  Electrodes: {self.lfm.shape[0]}")
        print(f"  Voxels: {self.lfm.shape[1]}")
        print(f"  Components: {self.lfm.shape[2]} (x, y, z)")
        print(f"Position shape: {self.positions.shape}")
        
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
        
        print(f"Saved leadfield to: {lfm_path}")
        print(f"Saved positions to: {pos_path}")
        
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
        
        print(f"Loaded leadfield: {self.lfm.shape}")
        print(f"Loaded positions: {self.positions.shape}")
        
        return self.lfm, self.positions


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

