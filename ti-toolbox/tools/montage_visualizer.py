#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Montage Visualizer
Author: Aksel W Jackson / awjackson2@wisc.edu
        Ido Haber / ihaber@wisc.edu

Optimized for TI-Toolbox analyzer.
This module creates PNG visualizations of electrode montages from user input.
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict


class ResourcePathManager:
    """
    Manages resource paths for the montage visualizer.
    Handles both production (/ti-toolbox) and development (/development) modes.
    """
    
    def __init__(self, project_dir_name: Optional[str] = None):
        """
        Initialize resource path manager.
        
        Args:
            project_dir_name: Name of the project directory (from PROJECT_DIR_NAME env var)
        """
        self.project_dir_name = project_dir_name or os.environ.get('PROJECT_DIR_NAME')
        self.resources_dir = self._detect_resources_dir()
        
    def _detect_resources_dir(self) -> str:
        """
        Detect the correct resources directory based on environment.
        
        Priority:
        1. Project directory: /mnt/{PROJECT_DIR_NAME}/code/ti-toolbox/resources/amv
        2. Development directory: /development/resources/amv  
        3. Production directory: /ti-toolbox/resources/amv (baked into Docker image)
        
        Returns:
            Path to resources/amv directory
        """
        # Priority 1: Check project directory first
        if self.project_dir_name:
            project_resources = f"/mnt/{self.project_dir_name}/code/ti-toolbox/resources/amv"
            if os.path.isdir(project_resources):
                return project_resources
        
        # Priority 2: Check development mode
        dev_resources = "/development/resources/amv"
        if os.path.isdir(dev_resources):
            return dev_resources
        
        # Priority 3: Fall back to production (Docker image location)
        prod_resources = "/ti-toolbox/resources/amv"
        if os.path.isdir(prod_resources):
            return prod_resources
        
        # If none found, raise error
        raise FileNotFoundError(
            f"Resources directory not found. Checked:\n"
            f"  1. /mnt/{self.project_dir_name}/code/ti-toolbox/resources/amv\n"
            f"  2. /development/resources/amv\n"
            f"  3. /ti-toolbox/resources/amv"
        )
    
    def get_coordinate_file(self, eeg_net: str) -> str:
        """
        Get the coordinate file path for a specific EEG net.

        Args:
            eeg_net: Name of the EEG net (e.g., "EGI_template.csv")

        Returns:
            Path to coordinate CSV file, or None for freehand/flex modes that don't use predefined coordinates

        Raises:
            ValueError: If EEG net is not supported
        """
        # Freehand and flex modes don't use predefined coordinate files
        if eeg_net in ["freehand", "flex_mode"]:
            return None

        # GSN-HD compatible nets
        gsn_hd_nets = [
            "EGI_template.csv",
            "GSN-HydroCel-185.csv",
            "GSN-HydroCel-256.csv"
        ]

        # 10-10 system nets
        ten_ten_nets = [
            "EEG10-10_UI_Jurak_2007.csv",
            "EEG10-10_Neuroelectrics.csv"
        ]

        if eeg_net in gsn_hd_nets:
            return os.path.join(self.resources_dir, "GSN-HD.csv")
        elif eeg_net in ten_ten_nets:
            return os.path.join(self.resources_dir, "10-10-net.csv")
        else:
            raise ValueError(f"Unsupported EEG net: {eeg_net}")
    
    def get_template_image(self, eeg_net: str) -> str:
        """
        Get the template image path for a specific EEG net.
        
        Args:
            eeg_net: Name of the EEG net
            
        Returns:
            Path to template PNG image
        """
        gsn_hd_nets = [
            "EGI_template.csv",
            "GSN-HydroCel-185.csv",
            "GSN-HydroCel-256.csv"
        ]
        
        if eeg_net in gsn_hd_nets:
            return os.path.join(self.resources_dir, "256template.png")
        else:
            return os.path.join(self.resources_dir, "10-10-net.png")
    
    def get_ring_image(self, pair_index: int) -> str:
        """
        Get the ring image for a specific pair index.
        
        Args:
            pair_index: Index of the electrode pair (0-based)
            
        Returns:
            Path to ring image
        """
        ring_images = [
            "pair1ring.png",
            "pair2ring.png", 
            "pair3ring.png",
            "pair4ring.png",
            "pair5ring.png",
            "pair6ring.png",
            "pair7ring.png",
            "pair8ring.png"
        ]
        
        # Cycle through available ring images
        ring_file = ring_images[pair_index % len(ring_images)]
        return os.path.join(self.resources_dir, ring_file)


class ElectrodeCoordinateReader:
    """Reads electrode coordinates from CSV files."""
    
    def __init__(self, coordinate_file: str):
        """
        Initialize coordinate reader.
        
        Args:
            coordinate_file: Path to coordinate CSV file
        """
        self.coordinate_file = coordinate_file
        self.is_gsn_hd = "GSN-HD" in coordinate_file
        
    def get_coordinates(self, electrode_label: str) -> Optional[Tuple[int, int]]:
        """
        Get coordinates for an electrode label.
        
        Args:
            electrode_label: Electrode label (e.g., "E020", "Fp1")
            
        Returns:
            Tuple of (x, y) coordinates, or None if not found
        """
        try:
            with open(self.coordinate_file, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if not parts:
                        continue
                    
                    if parts[0] == electrode_label:
                        if self.is_gsn_hd:
                            # GSN-HD format: name,xcord,modifiedxcord,ycord,modifiedycord
                            # Use columns 3,5 (indices 2,4)
                            if len(parts) >= 5:
                                return (int(float(parts[2])), int(float(parts[4])))
                        else:
                            # 10-10-net format: electrode_name,x,y
                            # Use columns 2,3 (indices 1,2)
                            if len(parts) >= 3:
                                return (int(float(parts[1])), int(float(parts[2])))
        except Exception as e:
            print(f"Warning: Error reading coordinates for {electrode_label}: {e}")
        
        return None


class MontageVisualizer:
    """Creates montage visualizations using ImageMagick."""
    
    def __init__(self,
                 montage_file: str,
                 resource_manager: ResourcePathManager,
                 eeg_net: str,
                 sim_mode: str,
                 output_directory: str,
                 verbose: bool = True):
        """
        Initialize montage visualizer.

        Args:
            montage_file: Path to montage_list.json
            resource_manager: ResourcePathManager instance
            eeg_net: EEG net name
            sim_mode: Simulation mode ('U' for unipolar, 'M' for multipolar)
            output_directory: Directory for output images
            verbose: Whether to print verbose output
        """
        self.montage_file = montage_file
        self.resource_manager = resource_manager
        self.eeg_net = eeg_net
        self.sim_mode = sim_mode
        self.output_directory = output_directory
        self.verbose = verbose

        # Check if this is a freehand/flex mode that doesn't use predefined coordinates
        self.skip_visualization = eeg_net in ["freehand", "flex_mode"]

        if self.skip_visualization:
            if self.verbose:
                print(f"Skipping montage visualization for {eeg_net} mode (arbitrary electrode positions)")
            return

        # Set up coordinate reader
        coord_file = resource_manager.get_coordinate_file(eeg_net)
        self.coord_reader = ElectrodeCoordinateReader(coord_file)

        # Get template image
        self.template_image = resource_manager.get_template_image(eeg_net)

        # Determine montage type
        self.montage_type = "uni_polar_montages" if sim_mode == "U" else "multi_polar_montages"

        # Create output directory
        os.makedirs(output_directory, exist_ok=True)

        # For multipolar mode, initialize combined output image
        self.combined_output_image = None
        if sim_mode == "M":
            self.combined_output_image = os.path.join(
                output_directory,
                "combined_montage_visualization.png"
            )
            self._copy_template(self.template_image, self.combined_output_image)
    
    def _log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(message)
    
    def _copy_template(self, source: str, dest: str):
        """Copy template image using ImageMagick convert."""
        try:
            subprocess.run(['cp', source, dest], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to copy template image: {e}")
    
    def _overlay_ring(self, 
                     output_image: str,
                     electrode_label: str, 
                     ring_image: str):
        """
        Overlay a ring on the output image at electrode coordinates.
        
        Args:
            output_image: Path to output image being modified
            electrode_label: Label of electrode to highlight
            ring_image: Path to ring image
        """
        # Get coordinates
        coords = self.coord_reader.get_coordinates(electrode_label)
        if coords is None:
            self._log(f"Warning: Coordinates not found for electrode '{electrode_label}'. Skipping overlay.")
            return
        
        x, y = coords
        self._log(f"Coordinates for electrode '{electrode_label}': x={x}, y={y}")
        
        # Use ImageMagick to overlay ring
        try:
            subprocess.run([
                'convert',
                output_image,
                ring_image,
                '-geometry', f'+{x}+{y}',
                '-composite',
                output_image
            ], check=True)
        except subprocess.CalledProcessError as e:
            self._log(f"Error: Failed to overlay ring image '{ring_image}' onto output image '{output_image}'.")
    
    def visualize_montages(self, montage_names: List[str]) -> bool:
        """
        Visualize selected montages.

        Args:
            montage_names: List of montage names to visualize

        Returns:
            True if successful, False otherwise
        """
        # Skip visualization for freehand/flex modes
        if self.skip_visualization:
            if self.verbose:
                print(f"Montage visualization skipped for {self.eeg_net} mode - arbitrary electrode positions cannot be visualized on standard templates")
            return True

        # Load montage configuration
        try:
            with open(self.montage_file, 'r') as f:
                montage_config = json.load(f)
        except Exception as e:
            print(f"Error: Failed to load montage file '{self.montage_file}': {e}")
            return False
        
        self._log(f"Using coordinate file: {self.coord_reader.coordinate_file} for EEG net: {self.eeg_net}")
        self._log(f"Simulation Mode (sim_mode): {self.sim_mode}")
        self._log(f"EEG Net: {self.eeg_net}")
        self._log(f"Montage Type: {self.montage_type}")
        self._log(f"Selected Montages: {montage_names}")
        self._log(f"Output Directory: {self.output_directory}")
        self._log(f"Using template image: {self.template_image} for EEG net: {self.eeg_net}")
        
        # Global pair index across all montages
        global_pair_index = 0
        
        # Process each montage
        for montage_name in montage_names:
            self._log(f"Retrieving pairs for montage '{montage_name}' of type '{self.montage_type}' from net '{self.eeg_net}' in '{self.montage_file}'")
            
            # Extract pairs from JSON
            try:
                pairs = montage_config['nets'][self.eeg_net][self.montage_type][montage_name]
            except KeyError as e:
                print(f"Error: Failed to find montage '{montage_name}' in configuration: {e}")
                continue
            
            self._log(f"Retrieved pairs for montage '{montage_name}':")
            for pair in pairs:
                self._log(f"  {pair}")
            
            # For unipolar mode, create separate output image for each montage
            if self.sim_mode == "U":
                output_image = os.path.join(
                    self.output_directory,
                    f"{montage_name}_highlighted_visualization.png"
                )
                self._copy_template(self.template_image, output_image)
            else:
                # For multipolar, use combined image
                output_image = self.combined_output_image
            
            # Process each pair
            for pair in pairs:
                if len(pair) != 2:
                    self._log(f"Warning: Expected 2 electrodes, got {len(pair)}. Skipping pair: {pair}")
                    continue
                
                self._log(f"Processing pair: {pair}")
                
                # Get ring image for this pair
                ring_image = self.resource_manager.get_ring_image(global_pair_index)
                
                # Overlay rings for both electrodes
                self._overlay_ring(output_image, pair[0], ring_image)
                self._overlay_ring(output_image, pair[1], ring_image)
                
                global_pair_index += 1
            
            # Log completion for unipolar mode
            if self.sim_mode == "U":
                self._log(f"Ring overlays for montage '{montage_name}' completed. Output saved to {output_image}.")
        
        # Log completion for multipolar mode
        if self.sim_mode == "M":
            self._log(f"Ring overlays for all montages combined. Output saved to {self.combined_output_image}.")
        
        return True


def main():
    """Main entry point for montage visualizer."""
    parser = argparse.ArgumentParser(
        description="Create PNG visualizations of electrode montages",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'montages',
        nargs='+',
        help='List of montage names to visualize'
    )
    
    parser.add_argument(
        '--sim-mode',
        '-s',
        required=True,
        choices=['U', 'M'],
        help='Simulation mode: U (Unipolar) or M (Multipolar)'
    )
    
    parser.add_argument(
        '--eeg-net',
        '-e',
        required=True,
        help='EEG net name (e.g., EGI_template.csv)'
    )
    
    parser.add_argument(
        '--output-dir',
        '-o',
        required=True,
        help='Output directory for visualization images'
    )
    
    parser.add_argument(
        '--montage-file',
        '-m',
        help='Path to montage_list.json (auto-detected if not provided)'
    )
    
    parser.add_argument(
        '--project-dir-name',
        '-p',
        help='Project directory name (from PROJECT_DIR_NAME env var if not provided)'
    )
    
    parser.add_argument(
        '--quiet',
        '-q',
        action='store_true',
        help='Suppress verbose output'
    )
    
    args = parser.parse_args()
    
    # Auto-detect montage file if not provided
    if args.montage_file is None:
        project_dir_name = args.project_dir_name or os.environ.get('PROJECT_DIR_NAME')
        if project_dir_name:
            args.montage_file = f"/mnt/{project_dir_name}/code/ti-toolbox/config/montage_list.json"
        else:
            # Try development mode
            if os.path.isfile("/development/ti-toolbox/config/montage_list.json"):
                args.montage_file = "/development/ti-toolbox/config/montage_list.json"
            else:
                args.montage_file = "/ti-toolbox/config/montage_list.json"
    
    # Check montage file exists
    if not os.path.isfile(args.montage_file):
        print(f"Error: Montage file not found at: {args.montage_file}")
        return 1
    
    try:
        # Initialize resource manager
        resource_manager = ResourcePathManager(args.project_dir_name)
        
        if not args.quiet:
            print(f"Using resources from: {resource_manager.resources_dir}")
        
        # Create visualizer
        visualizer = MontageVisualizer(
            montage_file=args.montage_file,
            resource_manager=resource_manager,
            eeg_net=args.eeg_net,
            sim_mode=args.sim_mode,
            output_directory=args.output_dir,
            verbose=not args.quiet
        )
        
        # Generate visualizations
        success = visualizer.visualize_montages(args.montages)
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

