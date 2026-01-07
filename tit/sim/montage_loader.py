#!/usr/bin/env simnibs_python
"""
Montage loading and validation utilities.
"""

import json
import os
from typing import Dict, List, Optional

from tit.sim.config import MontageConfig
from tit.core import get_path_manager
from tit.sim import utils as sim_utils


def load_montage_file(project_dir: str, eeg_net: str) -> Dict:
    """
    Load montage configuration file.

    Args:
        project_dir: Project directory path
        eeg_net: EEG net name

    Returns:
        Dictionary of montages for the specified EEG net
    """
    # Delegate montage_list.json management to shared sim utils (used by GUI + CLI).
    all_montages = sim_utils.load_montage_data(project_dir)
    nets = all_montages.get("nets") or {}
    if not isinstance(nets, dict):
        nets = {}
        all_montages["nets"] = nets
    # Never raise for missing EEG net; return empty structure (caller may create montages).
    net_data = nets.get(eeg_net)
    if not isinstance(net_data, dict):
        return {"uni_polar_montages": {}, "multi_polar_montages": {}}
    net_data.setdefault("uni_polar_montages", {})
    net_data.setdefault("multi_polar_montages", {})
    return net_data


def list_montage_names(project_dir: str, eeg_net: str, *, mode: str) -> List[str]:
    """
    List montage names for a given EEG net and mode.
    mode: 'U' (uni_polar_montages) or 'M' (multi_polar_montages)
    """
    # Use shared util (never throws for missing nets).
    return sim_utils.list_montage_names(project_dir, eeg_net, mode=mode)


def add_montage(
    *,
    project_dir: str,
    eeg_net: str,
    montage_name: str,
    electrode_pairs: List[List[str]],
    mode: str,
) -> None:
    """
    Persist a montage into montage_list.json under the given net.
    mode: 'U' (uni_polar_montages) or 'M' (multi_polar_montages)
    """
    # Delegate persistence to shared sim utils (used by GUI + CLI).
    sim_utils.upsert_montage(
        project_dir=project_dir,
        eeg_net=eeg_net,
        montage_name=montage_name,
        electrode_pairs=electrode_pairs,
        mode=mode,
    )


def load_flex_montages(flex_file: Optional[str] = None) -> List[Dict]:
    """
    Load flex/freehand montages from environment or file.

    Args:
        flex_file: Optional path to flex montages file

    Returns:
        List of flex montage configurations
    """
    if not flex_file:
        flex_file = os.environ.get('FLEX_MONTAGES_FILE')

    if not flex_file or not os.path.exists(flex_file):
        return []

    with open(flex_file, 'r') as f:
        flex_config = json.load(f)

    # Handle different flex config formats
    if isinstance(flex_config, list):
        return flex_config
    elif 'montage' in flex_config:
        return [flex_config['montage']]
    else:
        return [flex_config]


def parse_flex_montage(flex_data: Dict) -> MontageConfig:
    """
    Parse flex montage data into MontageConfig.

    Args:
        flex_data: Flex montage dictionary

    Returns:
        MontageConfig object
    """
    montage_name = flex_data['name']
    montage_type = flex_data['type']

    if montage_type == 'flex_mapped':
        # Electrode names from EEG cap
        pairs_data = flex_data['pairs']
        electrode_pairs = [
            (pairs_data[0][0], pairs_data[0][1]),
            (pairs_data[1][0], pairs_data[1][1])
        ]
        return MontageConfig(
            name=montage_name,
            electrode_pairs=electrode_pairs,
            is_xyz=False,
            eeg_net=flex_data.get('eeg_net')
        )

    elif montage_type in ['flex_optimized', 'freehand_xyz']:
        # XYZ coordinates
        ep = flex_data['electrode_positions']
        electrode_pairs = [
            (ep[0], ep[1]),
            (ep[2], ep[3])
        ]
        return MontageConfig(
            name=montage_name,
            electrode_pairs=electrode_pairs,
            is_xyz=True
        )

    else:
        raise ValueError(f"Unknown flex montage type: {montage_type}")


def load_montages(
    montage_names: List[str],
    project_dir: str,
    eeg_net: str,
    include_flex: bool = True
) -> List[MontageConfig]:
    """
    Load all montages (regular + flex).

    Args:
        montage_names: List of montage names to load
        project_dir: Project directory path
        eeg_net: EEG net name
        include_flex: Whether to include flex montages

    Returns:
        List of MontageConfig objects
    """
    montages = []

    # Load regular montages
    net_montages = load_montage_file(project_dir, eeg_net)

    for name in montage_names:
        # Try multi_polar first, then uni_polar
        montage_data = net_montages.get('multi_polar_montages', {}).get(name)
        if not montage_data:
            montage_data = net_montages.get('uni_polar_montages', {}).get(name)

        if montage_data:
            # Determine if freehand mode (XYZ coordinates)
            is_xyz = eeg_net in ["freehand", "flex_mode"]

            montages.append(MontageConfig(
                name=name,
                electrode_pairs=montage_data,
                is_xyz=is_xyz,
                eeg_net=eeg_net
            ))

    # Load flex montages
    if include_flex:
        flex_montages = load_flex_montages()
        for flex_data in flex_montages:
            try:
                montages.append(parse_flex_montage(flex_data))
            except Exception as e:
                print(f"Warning: Failed to parse flex montage: {e}")

    return montages
