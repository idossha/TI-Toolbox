#!/usr/bin/env simnibs_python
"""
Standalone electrode mapping tool for TI-Toolbox.

This tool maps optimized electrode positions to the nearest available positions
in an EEG net loaded from a CSV file using the Hungarian algorithm (linear sum
assignment) for optimal matching.

Author: TI-Toolbox Team
"""

import os
import sys
import json
import argparse
import numpy as np
from scipy.optimize import linear_sum_assignment


def read_csv_positions(csv_path):
    """
    Read electrode positions from a CSV file using SimNIBS utilities.

    Parameters
    ----------
    csv_path : str
        Path to the file containing electrode positions.

    Returns
    -------
    positions : np.ndarray
        Array of electrode positions (Nx3).
    labels : list
        List of electrode labels/names.
    """
    from simnibs.utils.csv_reader import read_csv_positions as simnibs_read_csv

    # Use SimNIBS's CSV reader
    type_, coordinates, extra, name, extra_cols, header = simnibs_read_csv(csv_path)

    # Extract positions and names for electrodes only
    positions = []
    labels = []

    for t, coord, n in zip(type_, coordinates, name):
        if t in ["Electrode", "ReferenceElectrode"]:
            positions.append(coord)
            labels.append(n if n else f"E{len(positions)}")

    return np.array(positions), labels


def load_electrode_positions_json(json_path):
    """
    Load optimized electrode positions from electrode_positions.json.

    Parameters
    ----------
    json_path : str
        Path to the electrode_positions.json file.

    Returns
    -------
    positions : np.ndarray
        Array of optimized electrode positions (Nx3).
    channel_array_indices : list
        List of [channel, array] indices for each electrode.
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    positions = np.array(data["optimized_positions"])
    channel_array_indices = data["channel_array_indices"]

    return positions, channel_array_indices


def map_electrodes_to_net(
    optimized_positions, net_positions, net_labels, channel_array_indices
):
    """
    Map optimized electrode positions to nearest EEG net positions using
    the Hungarian algorithm for optimal assignment.

    Parameters
    ----------
    optimized_positions : np.ndarray
        Array of optimized electrode positions (Nx3).
    net_positions : np.ndarray
        Array of EEG net electrode positions (Mx3).
    net_labels : list
        List of EEG net electrode labels.
    channel_array_indices : list
        List of [channel, array] indices for each optimized electrode.

    Returns
    -------
    mapping_result : dict
        Dictionary containing:
        - optimized_positions: Original optimized positions
        - mapped_positions: Corresponding net positions
        - mapped_labels: Labels of mapped net electrodes
        - distances: Distances between optimized and mapped positions
        - channel_array_indices: Channel and array indices
    """
    print("Calculating distance matrix...")
    distance_matrix = np.array(
        [
            [np.linalg.norm(opt_pos - net_pos) for net_pos in net_positions]
            for opt_pos in optimized_positions
        ]
    )

    print("Finding optimal electrode assignment using Hungarian algorithm...")
    row_ind, col_ind = linear_sum_assignment(distance_matrix)

    mapping_result = {
        "optimized_positions": [optimized_positions[i].tolist() for i in row_ind],
        "mapped_positions": [net_positions[j].tolist() for j in col_ind],
        "mapped_labels": [net_labels[j] for j in col_ind],
        "distances": [distance_matrix[i, j] for i, j in zip(row_ind, col_ind)],
        "channel_array_indices": [channel_array_indices[i] for i in row_ind],
    }

    return mapping_result


def save_mapping_result(mapping_result, output_path, eeg_net_name=None):
    """
    Save mapping result to a JSON file.

    Parameters
    ----------
    mapping_result : dict
        Dictionary containing mapping information.
    output_path : str
        Path where to save the JSON file.
    eeg_net_name : str, optional
        Name of the EEG net file used.
    """
    json_data = mapping_result.copy()
    if eeg_net_name:
        json_data["eeg_net"] = eeg_net_name

    with open(output_path, "w") as f:
        json.dump(json_data, f, indent=2)

    print(f"Mapping data saved to: {output_path}")


def print_mapping_summary(mapping_result):
    """
    Print a summary of the electrode mapping results.

    Parameters
    ----------
    mapping_result : dict
        Dictionary containing mapping information.
    """
    print("\n" + "=" * 80)
    print("ELECTRODE MAPPING SUMMARY")
    print("=" * 80)

    total_distance = sum(mapping_result["distances"])
    avg_distance = (
        total_distance / len(mapping_result["distances"])
        if mapping_result["distances"]
        else 0
    )
    max_distance = (
        max(mapping_result["distances"]) if mapping_result["distances"] else 0
    )

    print(f"\nTotal electrodes mapped: {len(mapping_result['mapped_labels'])}")
    print(f"Average distance: {avg_distance:.2f} mm")
    print(f"Maximum distance: {max_distance:.2f} mm")
    print(f"Total distance: {total_distance:.2f} mm")

    print("\nDetailed mapping:")
    print("-" * 80)
    print(
        f"{'Idx':<5} {'Channel':<8} {'Array':<6} {'Mapped Label':<15} {'Distance (mm)':<15}"
    )
    print("-" * 80)

    for i, (label, dist, indices) in enumerate(
        zip(
            mapping_result["mapped_labels"],
            mapping_result["distances"],
            mapping_result["channel_array_indices"],
        )
    ):
        channel, array = indices
        print(f"{i:<5} {channel:<8} {array:<6} {label:<15} {dist:<15.2f}")

    print("=" * 80 + "\n")


def main():
    """Main function for standalone electrode mapping tool."""
    parser = argparse.ArgumentParser(
        description="Map optimized electrode positions to EEG net positions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Map using electrode_positions.json and EEG net CSV
  %(prog)s -i electrode_positions.json -n GSN-HydroCel-185.csv -o electrode_mapping.json

  # With verbose output
  %(prog)s -i electrode_positions.json -n GSN-HydroCel-185.csv -o electrode_mapping.json -v
        """,
    )

    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to electrode_positions.json file containing optimized positions",
    )

    parser.add_argument(
        "-n",
        "--net",
        required=True,
        help="Path to EEG net CSV file containing electrode positions",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="electrode_mapping.json",
        help="Output path for mapping result JSON file (default: electrode_mapping.json)",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print detailed mapping summary"
    )

    args = parser.parse_args()

    # Validate input files
    if not os.path.isfile(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.net):
        print(f"Error: EEG net file not found: {args.net}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading optimized electrode positions from: {args.input}")
    try:
        optimized_positions, channel_array_indices = load_electrode_positions_json(
            args.input
        )
        print(f"  Loaded {len(optimized_positions)} optimized electrode positions")
    except Exception as e:
        print(f"Error loading electrode positions: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nLoading EEG net positions from: {args.net}")
    try:
        net_positions, net_labels = read_csv_positions(args.net)
        print(f"  Loaded {len(net_positions)} EEG net electrode positions")
    except Exception as e:
        print(f"Error loading EEG net positions: {e}", file=sys.stderr)
        sys.exit(1)

    if len(optimized_positions) > len(net_positions):
        print(
            f"\nWarning: More optimized electrodes ({len(optimized_positions)}) than available net positions ({len(net_positions)})"
        )
        print("Some electrodes will not be mapped optimally.")

    print("\nPerforming electrode mapping...")
    mapping_result = map_electrodes_to_net(
        optimized_positions, net_positions, net_labels, channel_array_indices
    )

    eeg_net_name = os.path.basename(args.net)
    save_mapping_result(mapping_result, args.output, eeg_net_name)

    if args.verbose:
        print_mapping_summary(mapping_result)
    else:
        total_distance = sum(mapping_result["distances"])
        avg_distance = (
            total_distance / len(mapping_result["distances"])
            if mapping_result["distances"]
            else 0
        )
        print(f"\nMapping complete! Average distance: {avg_distance:.2f} mm")

    print(f"\nSuccess! Mapping saved to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
