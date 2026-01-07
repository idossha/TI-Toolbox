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
    Handles both production (/tit) and development (/development) modes.
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
        Return the resources directory.

        TI-Toolbox is expected to run with the repository mounted at `/ti-toolbox`,
        so resources are always located at:
            /ti-toolbox/resources/amv

        Returns:
            Path to `/ti-toolbox/resources/amv`
        """
        resources = "/ti-toolbox/resources/amv"
        if not os.path.isdir(resources):
            raise FileNotFoundError(f"Resources directory not found: {resources}")
        return resources
    
    def get_coordinate_file(self, eeg_net: str) -> Optional[str]:
        """
        Get the coordinate file path for a specific EEG net.

        Args:
            eeg_net: Name of the EEG net (e.g., "GSN-HydroCel-185.csv")

        Returns:
            Path to coordinate CSV file, or None for freehand/flex modes or explicitly unsupported nets.

        Raises:
            ValueError: If `eeg_net` is not recognized.
        """
        # Freehand and flex modes don't use predefined coordinate files
        if eeg_net in ["freehand", "flex_mode"]:
            return None

        # Unsupported nets that don't have visualization support
        unsupported_nets = [
            "easycap_BC_TMS64_X21.csv",
            "EEG10-20_extended_SPM12"
        ]

        if eeg_net in unsupported_nets:
            return None

        # GSN-HD compatible nets
        gsn_hd_nets = [
            "GSN-HydroCel-185.csv",
            "GSN-HydroCel-256.csv",
            "GSN-HydroCel-185"  # Legacy alias for GSN-HydroCel-185
        ]

        # 10-10 system nets
        ten_ten_nets = [
            "EEG10-10_UI_Jurak_2007.csv",
            "EEG10-10_Cutini_2011.csv",
            "EEG10-20_Okamoto_2004.csv",
            "EEG10-10_Neuroelectrics.csv"
        ]

        if eeg_net in gsn_hd_nets:
            return os.path.join(self.resources_dir, "GSN-256.csv")
        elif eeg_net in ten_ten_nets:
            return os.path.join(self.resources_dir, "10-10.csv")
        else:
            # Unknown net: fail fast rather than silently skipping visualization.
            # This avoids "false green" runs where montage images are missing.
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
            "GSN-HydroCel-185.csv",
            "GSN-HydroCel-256.csv",
            "GSN-HydroCel-185"  # Legacy alias for GSN-HydroCel-185
        ]

        # All nets use the same GSN-256 template image
        return os.path.join(self.resources_dir, "GSN-256.png")
    
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
        # GSN-HD format has 5 columns, others have 3 columns
        self.is_gsn_hd = False  # All our current files use 3-column format

        # Cache all coordinates for efficiency
        self._coordinate_cache = self._load_all_coordinates()

    def _load_all_coordinates(self) -> Dict[str, Tuple[int, int]]:
        """
        Load all electrode coordinates into memory for fast lookup.

        Returns:
            Dictionary mapping electrode labels to (x, y) coordinate tuples
        """
        coordinates = {}
        try:
            with open(self.coordinate_file, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if not parts:
                        continue

                    electrode_label = parts[0]

                    # Skip header row or invalid electrode names
                    if electrode_label in ['electrode_name', 'name', ''] or not electrode_label:
                        continue

                    try:
                        if self.is_gsn_hd:
                            # GSN-HD format: name,xcord,modifiedxcord,ycord,modifiedycord
                            # Use columns 3,5 (indices 2,4)
                            if len(parts) >= 5:
                                coords = (int(float(parts[2])), int(float(parts[4])))
                                coordinates[electrode_label] = coords
                        else:
                            # 10-10-net format: electrode_name,x,y
                            # Use columns 2,3 (indices 1,2)
                            if len(parts) >= 3:
                                coords = (int(float(parts[1])), int(float(parts[2])))
                                coordinates[electrode_label] = coords
                    except (ValueError, IndexError) as e:
                        print(f"Warning: Error parsing coordinates for {electrode_label}: {e}")
                        continue
        except Exception as e:
            print(f"Warning: Error loading coordinate file {self.coordinate_file}: {e}")

        return coordinates

    def get_coordinates(self, electrode_label: str) -> Optional[Tuple[int, int]]:
        """
        Get coordinates for an electrode label.

        Args:
            electrode_label: Electrode label (e.g., "E020", "Fp1")

        Returns:
            Tuple of (x, y) coordinates, or None if not found
        """
        return self._coordinate_cache.get(electrode_label)


class MontageVisualizer:
    """Creates montage visualizations using ImageMagick."""

    # Class constants for efficiency - professional, visually distinct, brighter colors for scientific visualization
    COLOR_MAP = [
        'blue',            # pair 0 - brighter blue
        'red',             # pair 1 - brighter red
        'green',           # pair 2 - brighter green
        'purple',          # pair 3 - distinct purple
        'orange',          # pair 4 - brighter orange
        'cyan',            # pair 5 - brighter cyan
        'chocolate',       # pair 6 - brighter brown
        'violet'           # pair 7 - brighter purple-violet
    ]

    def __init__(self,
                 montage_file: str,
                 resource_manager: ResourcePathManager,
                 eeg_net: str,
                 sim_mode: str,
                 output_directory: str,
                 verbose: bool = True,
                 montage_data: Optional[Dict[str, List[List[str]]]] = None):
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
        self.montage_data = montage_data

        # Check if this is a freehand/flex mode or unsupported EEG net
        self.skip_visualization = eeg_net in ["freehand", "flex_mode"]

        if self.skip_visualization:
            if self.verbose:
                print(f"Skipping montage visualization for {eeg_net} mode (arbitrary electrode positions)")
            return

        # Set up coordinate reader
        coord_file = resource_manager.get_coordinate_file(eeg_net)

        # Check if EEG net is unsupported (coord_file is None)
        if coord_file is None:
            self.skip_visualization = True
            if self.verbose:
                print(f"Skipping montage visualization for {eeg_net} (unsupported EEG net)")
            return

        self.coord_reader = ElectrodeCoordinateReader(coord_file)

        # Cache base ring path for efficiency
        self.base_ring = resource_manager.get_ring_image(0)

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
                     pair_index: int):
        """
        Overlay a colorized ring on the output image at electrode coordinates.

        Args:
            output_image: Path to output image being modified
            electrode_label: Label of electrode to highlight
            pair_index: Index of the electrode pair (used to determine color)
        """
        # Get coordinates
        coords = self.coord_reader.get_coordinates(electrode_label)
        if coords is None:
            self._log(f"Warning: Coordinates not found for electrode '{electrode_label}'. Skipping overlay.")
            return

        x, y = coords
        self._log(f"Coordinates for electrode '{electrode_label}': x={x}, y={y}")

        # Get the ring color from the pair index (same as connection lines)
        ring_color = self.COLOR_MAP[pair_index % len(self.COLOR_MAP)]

        # Use cached base ring template

        # New ring images are 100x100 with the ring centered at (50,50)
        # To center the ring on electrode coordinates (x,y),
        # place the ring image at (x-50, y-50)
        adjusted_x = x - 50
        adjusted_y = y - 50

        self._log(f"Adjusted position for ring centering: x={adjusted_x}, y={adjusted_y}")
        self._log(f"Using color '{ring_color}' for ring overlay")

        # Use ImageMagick to colorize and overlay ring
        try:
            subprocess.run([
                'convert',
                output_image,
                '(',
                self.base_ring,
                '-fill', ring_color,
                '-colorize', '100,100,100',  # Fully colorize the ring
                ')',
                '-geometry', f'+{adjusted_x}+{adjusted_y}',
                '-composite',
                output_image
            ], check=True)
        except subprocess.CalledProcessError as e:
            self._log(f"Error: Failed to overlay colorized ring onto output image '{output_image}'.")

    def _draw_connection_line(self,
                             output_image: str,
                             electrode1: str,
                             electrode2: str,
                             pair_index: int):
        """
        Draw an arched connection line between two electrodes using the same color as their rings.

        Args:
            output_image: Path to output image being modified
            electrode1: Name of first electrode
            electrode2: Name of second electrode
            pair_index: Index of the electrode pair (used to determine color)
        """
        # Get coordinates for both electrodes
        coords1 = self.coord_reader.get_coordinates(electrode1)
        coords2 = self.coord_reader.get_coordinates(electrode2)

        if coords1 is None or coords2 is None:
            self._log(f"Warning: Could not get coordinates for electrodes '{electrode1}' or '{electrode2}'. Skipping connection line.")
            return

        x1, y1 = coords1
        x2, y2 = coords2

        self._log(f"Drawing connection line between '{electrode1}' ({x1},{y1}) and '{electrode2}' ({x2},{y2})")

        # Determine the line color from the pair index (same as rings)
        line_color = self.COLOR_MAP[pair_index % len(self.COLOR_MAP)]

        # Calculate vector between electrodes
        dx = x2 - x1
        dy = y2 - y1
        distance = (dx**2 + dy**2)**0.5

        if distance > 0:
            # Normalize the vector
            unit_x = dx / distance
            unit_y = dy / distance

            # Offset start and end points by -15px from electrode centers
            offset_distance = 15
            start_x = x1 + unit_x * offset_distance  # Move away from electrode 1
            start_y = y1 + unit_y * offset_distance
            end_x = x2 - unit_x * offset_distance    # Move away from electrode 2
            end_y = y2 - unit_y * offset_distance

            # Calculate control point for quadratic bezier curve (creates an arch)
            # Control point is midway between the offset points, lifted up by a quarter of the distance
            mid_x = (start_x + end_x) / 2
            mid_y = (start_y + end_y) / 2
            arch_height = distance * 0.25  # 25% of distance for nice arch

            # Calculate perpendicular direction for arch
            perp_x = -dy / distance
            perp_y = dx / distance

            control_x = mid_x + perp_x * arch_height
            control_y = mid_y + perp_y * arch_height

            # Draw the arched line using ImageMagick
            try:
                subprocess.run([
                    'convert',
                    output_image,
                    '-stroke', line_color,
                    '-strokewidth', '3',
                    '-fill', 'none',
                    '-draw', f'bezier {start_x},{start_y} {control_x},{control_y} {end_x},{end_y}',
                    output_image
                ], check=True)
                self._log(f"Connection line drawn in {line_color} with 15px offset")
            except subprocess.CalledProcessError as e:
                self._log(f"Error: Failed to draw connection line on output image '{output_image}'.")
        else:
            self._log(f"Warning: Electrodes are at the same position, skipping connection line.")

    def visualize_montages(self, montage_names: List[str]) -> bool:
        """
        Visualize selected montages.

        Args:
            montage_names: List of montage names to visualize

        Returns:
            True if successful, False otherwise
        """
        # Skip visualization for freehand/flex modes or unsupported nets
        if self.skip_visualization:
            if self.verbose:
                print(f"Montage visualization skipped for {self.eeg_net} mode")
            return True

        # Load montage configuration if not using direct data
        montage_config = None
        if not self.montage_data:
            try:
                with open(self.montage_file, 'r') as f:
                    montage_config = json.load(f)
            except Exception as e:
                print(f"Error: Failed to load montage file '{self.montage_file}': {e}")
                return False

        # Only log coordinate file info if coord_reader was created (not skipped)
        if hasattr(self, 'coord_reader') and self.coord_reader:
            self._log(f"Using coordinate file: {self.coord_reader.coordinate_file} for EEG net: {self.eeg_net}")
        self._log(f"Simulation Mode (sim_mode): {self.sim_mode}")
        self._log(f"EEG Net: {self.eeg_net}")
        if hasattr(self, 'montage_type'):
            self._log(f"Montage Type: {self.montage_type}")
        self._log(f"Selected Montages: {montage_names}")
        self._log(f"Output Directory: {self.output_directory}")
        if hasattr(self, 'template_image') and self.template_image:
            self._log(f"Using template image: {self.template_image} for EEG net: {self.eeg_net}")
        
        # Global pair index across all montages
        global_pair_index = 0
        
        # Process each montage
        for montage_name in montage_names:
            self._log(f"Retrieving pairs for montage '{montage_name}'")
            
            # Get pairs either from direct data or from JSON
            if self.montage_data and montage_name in self.montage_data:
                pairs = self.montage_data[montage_name]
            elif montage_config:
                # Extract pairs from JSON
                try:
                    pairs = montage_config['nets'][self.eeg_net][self.montage_type][montage_name]
                except KeyError as e:
                    print(f"Error: Failed to find montage '{montage_name}' in configuration: {e}")
                    continue
            else:
                print(f"Error: No montage data available for '{montage_name}'")
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

                # Overlay rings for both electrodes (colorized based on pair index)
                self._overlay_ring(output_image, pair[0], global_pair_index)
                self._overlay_ring(output_image, pair[1], global_pair_index)

                # Draw connection line between the electrodes
                self._draw_connection_line(output_image, pair[0], pair[1], global_pair_index)

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
        nargs='*',
        help='List of montage names to visualize (not used if --pairs is provided)'
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
        help='EEG net name (e.g., GSN-HydroCel-185.csv)'
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
        '--pairs',
        help='Montage pairs in format "montage_name:electrode1-electrode2,electrode3-electrode4"'
    )

    parser.add_argument(
        '--quiet',
        '-q',
        action='store_true',
        help='Suppress verbose output'
    )
    
    args = parser.parse_args()

    # Handle pairs argument
    if args.pairs:
        # Parse pairs format: "montage_name:electrode1-electrode2,electrode3-electrode4"
        try:
            montage_name, pairs_str = args.pairs.split(':', 1)
            pair_strings = pairs_str.split(',')
            pairs = []
            for pair_str in pair_strings:
                electrode1, electrode2 = pair_str.split('-')
                pairs.append([electrode1.strip(), electrode2.strip()])
            montage_data = {montage_name: pairs}
        except ValueError as e:
            print(f"Error parsing --pairs argument: {e}")
            print("Expected format: --pairs 'montage_name:electrode1-electrode2,electrode3-electrode4'")
            return 1
    else:
        montage_data = None

    # Auto-detect montage file if not provided
    if args.montage_file is None:
        project_dir_name = args.project_dir_name or os.environ.get('PROJECT_DIR_NAME')
        if project_dir_name:
            args.montage_file = f"/mnt/{project_dir_name}/code/tit/config/montage_list.json"
        else:
            # Try development mode
            if os.path.isfile("/development/tit/config/montage_list.json"):
                args.montage_file = "/development/tit/config/montage_list.json"
            else:
                args.montage_file = "/tit/config/montage_list.json"
    
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
            verbose=not args.quiet,
            montage_data=montage_data if args.pairs else None
        )

        # Generate visualizations
        montage_names = [montage_name] if args.pairs else args.montages
        success = visualizer.visualize_montages(montage_names)
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

