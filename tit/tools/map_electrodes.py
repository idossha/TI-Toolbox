"""Map optimised electrode positions to the nearest EEG net electrodes.

Uses the Hungarian algorithm (``scipy.optimize.linear_sum_assignment``)
to find the globally optimal one-to-one assignment between optimised
coordinates produced by the flex-search optimiser and the physical
electrode sites in a SimNIBS EEG net CSV file.

See Also
--------
tit.opt.flex : Differential-evolution flex-search optimiser.
tit.tools.montage_visualizer : Render montage placement as PNG.
"""

import csv
import json
import logging
from collections import Counter

import numpy as np
from scipy.optimize import linear_sum_assignment

logger = logging.getLogger(__name__)


def read_csv_positions(csv_path):
    """
    Read the stimulation electrodes of a SimNIBS EEG net CSV.

    The rule every net reader in TI-Toolbox shares (the catalog's net
    pickers, job preflight, simulation coordinates, the electrode overlay):
    ``Electrode,x,y,z,label`` rows only. ``ReferenceElectrode`` (Cz in the
    10-10 and SPM12 caps) and ``Fiducial`` rows are not offered as
    stimulation electrodes anywhere else, so a mapping onto them would name
    a label that preflight then refuses. Rows with fewer than five cells (a
    blank line) are skipped rather than failing the whole net.

    Parameters
    ----------
    csv_path : str
        Path to the file containing electrode positions.

    Returns
    -------
    positions : np.ndarray
        Array of electrode positions (Nx3).
    labels : list of str
        List of electrode labels/names.

    See Also
    --------
    load_electrode_positions_json : Load positions from optimiser output.
    """
    positions = []
    labels = []
    with open(csv_path, newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 5 and row[0].strip().lower() == "electrode":
                positions.append([float(row[1]), float(row[2]), float(row[3])])
                labels.append(row[4].strip())

    return np.array(positions, dtype=float).reshape(-1, 3), labels


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
    channel_array_indices : list of list
        List of ``[channel, array]`` indices for each electrode.

    See Also
    --------
    read_csv_positions : Load positions from a SimNIBS EEG net CSV.
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    positions = np.array(data["optimized_positions"])
    channel_array_indices = data["channel_array_indices"]

    return positions, channel_array_indices


def check_net_for_mapping(net_positions, net_labels, n_electrodes, net_name):
    """Refuse a net the optimised electrodes cannot be mapped onto, naming the defect.

    The assignment puts each optimised electrode on its own net site, so the net
    needs at least *n_electrodes* stimulation electrodes (``Electrode`` rows: a
    Fiducials file or a header-less ``Label,X,Y,Z`` list has none), finite
    coordinates (a NaN distance makes the assignment meaningless) and distinct
    labels (a repeated label would put two electrodes on one named site).

    Parameters
    ----------
    net_positions : np.ndarray
        Net electrode positions (Mx3), as :func:`read_csv_positions` returns them.
    net_labels : list of str
        Net electrode labels, in the same order.
    n_electrodes : int
        Number of optimised electrodes to place.
    net_name : str
        The net's file name, for the message.

    Raises
    ------
    ValueError
        Naming *net_name* and the first defect found.
    """
    positions = np.asarray(net_positions, dtype=float).reshape(-1, 3)
    if not net_labels:
        raise ValueError(
            f"EEG net {net_name} has no stimulation electrodes (no 'Electrode' rows), "
            "so nothing can be mapped onto it"
        )
    if len(net_labels) < n_electrodes:
        raise ValueError(
            f"EEG net {net_name} has {len(net_labels)} stimulation electrodes; "
            f"the run placed {n_electrodes}, each needing its own site"
        )
    bad = [lab for lab, p in zip(net_labels, positions) if not np.isfinite(p).all()]
    if bad:
        raise ValueError(
            f"EEG net {net_name} has non-finite coordinates for {', '.join(bad)}"
        )
    repeated = sorted(lab for lab, n in Counter(net_labels).items() if n > 1)
    if repeated:
        raise ValueError(
            f"EEG net {net_name} repeats the label {', '.join(repeated)}: "
            "each electrode needs a name of its own"
        )


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
