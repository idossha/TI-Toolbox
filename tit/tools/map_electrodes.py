"""
Electrode mapping utilities for TI-Toolbox.

Maps optimized electrode positions to the nearest available positions
in an EEG net using the Hungarian algorithm (linear sum assignment)
for optimal matching.
"""

import json
import logging

import numpy as np
from scipy.optimize import linear_sum_assignment

logger = logging.getLogger(__name__)


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
    logger.info("Calculating distance matrix...")
    distance_matrix = np.array(
        [
            [np.linalg.norm(opt_pos - net_pos) for net_pos in net_positions]
            for opt_pos in optimized_positions
        ]
    )

    logger.info("Finding optimal electrode assignment using Hungarian algorithm...")
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

    logger.info("Mapping data saved to: %s", output_path)


def log_mapping_summary(mapping_result):
    """
    Log a summary of the electrode mapping results.

    Parameters
    ----------
    mapping_result : dict
        Dictionary containing mapping information.
    """
    total_distance = sum(mapping_result["distances"])
    avg_distance = (
        total_distance / len(mapping_result["distances"])
        if mapping_result["distances"]
        else 0
    )
    max_distance = (
        max(mapping_result["distances"]) if mapping_result["distances"] else 0
    )

    logger.info("=" * 80)
    logger.info("ELECTRODE MAPPING SUMMARY")
    logger.info("=" * 80)
    logger.info("Total electrodes mapped: %d", len(mapping_result["mapped_labels"]))
    logger.info("Average distance: %.2f mm", avg_distance)
    logger.info("Maximum distance: %.2f mm", max_distance)
    logger.info("Total distance: %.2f mm", total_distance)

    logger.info("Detailed mapping:")
    logger.info("-" * 80)
    logger.info(
        "%-5s %-8s %-6s %-15s %-15s",
        "Idx",
        "Channel",
        "Array",
        "Mapped Label",
        "Distance (mm)",
    )
    logger.info("-" * 80)

    for i, (label, dist, indices) in enumerate(
        zip(
            mapping_result["mapped_labels"],
            mapping_result["distances"],
            mapping_result["channel_array_indices"],
        )
    ):
        channel, array = indices
        logger.info("%-5d %-8s %-6s %-15s %-15.2f", i, channel, array, label, dist)

    logger.info("=" * 80)
