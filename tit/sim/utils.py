#!/usr/bin/env simnibs_python
"""
Shared utilities for simulation-related IO (used by both CLI and GUI).

Currently:
- Montage list management (code/tit/config/montage_list.json)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def montage_config_dir(project_dir: str) -> str:
    return os.path.join(project_dir, "code", "tit", "config")


def montage_list_path(project_dir: str) -> str:
    return os.path.join(montage_config_dir(project_dir), "montage_list.json")


def _chmod_best_effort(path: str, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except Exception:
        pass


def ensure_montage_file(project_dir: str) -> str:
    """
    Ensure montage_list.json exists with a valid schema.

    Returns the montage_list.json path.
    """
    config_dir = montage_config_dir(project_dir)
    os.makedirs(config_dir, exist_ok=True)

    # Best-effort permissive perms (matches GUI expectations in containers)
    _chmod_best_effort(os.path.join(project_dir, "code", "tit"), 0o777)
    _chmod_best_effort(config_dir, 0o777)

    path = montage_list_path(project_dir)
    if not os.path.exists(path):
        initial_content = {
            "nets": {
                "EEG10-10_UI_Jurak_2007.csv": {
                    "uni_polar_montages": {},
                    "multi_polar_montages": {},
                }
            }
        }
        with open(path, "w") as f:
            json.dump(initial_content, f, indent=4)

    _chmod_best_effort(path, 0o777)
    return path


def load_montage_data(project_dir: str) -> Dict[str, Any]:
    """Load montage_list.json (creating it if missing)."""
    path = ensure_montage_file(project_dir)
    with open(path, "r") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("nets", {})
    if not isinstance(data["nets"], dict):
        data["nets"] = {}
    return data


def save_montage_data(project_dir: str, data: Dict[str, Any]) -> None:
    """Write montage_list.json (best-effort chmod)."""
    path = ensure_montage_file(project_dir)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    _chmod_best_effort(path, 0o777)


def ensure_eeg_net_entry(project_dir: str, eeg_net: str) -> None:
    """Ensure the given EEG net exists in montage_list.json."""
    data = load_montage_data(project_dir)
    nets = data.setdefault("nets", {})
    if eeg_net not in nets:
        nets[eeg_net] = {"uni_polar_montages": {}, "multi_polar_montages": {}}
    else:
        if not isinstance(nets[eeg_net], dict):
            nets[eeg_net] = {"uni_polar_montages": {}, "multi_polar_montages": {}}
        nets[eeg_net].setdefault("uni_polar_montages", {})
        nets[eeg_net].setdefault("multi_polar_montages", {})
    save_montage_data(project_dir, data)


def upsert_montage(
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
    data = load_montage_data(project_dir)
    nets = data.setdefault("nets", {})
    if eeg_net not in nets or not isinstance(nets.get(eeg_net), dict):
        nets[eeg_net] = {"uni_polar_montages": {}, "multi_polar_montages": {}}
    nets[eeg_net].setdefault("uni_polar_montages", {})
    nets[eeg_net].setdefault("multi_polar_montages", {})

    key = "uni_polar_montages" if mode.upper() == "U" else "multi_polar_montages"
    if not isinstance(nets[eeg_net].get(key), dict):
        nets[eeg_net][key] = {}
    nets[eeg_net][key][montage_name] = electrode_pairs
    save_montage_data(project_dir, data)


def list_montage_names(project_dir: str, eeg_net: str, *, mode: str) -> List[str]:
    """
    List montage names for a given EEG net and mode.
    Never raises for missing EEG nets; returns [].
    """
    data = load_montage_data(project_dir)
    nets = data.get("nets") or {}
    net_montages = nets.get(eeg_net) if isinstance(nets, dict) else None
    if not isinstance(net_montages, dict):
        return []
    key = "uni_polar_montages" if mode.upper() == "U" else "multi_polar_montages"
    names = list((net_montages.get(key) or {}).keys()) if isinstance(net_montages.get(key), dict) else []
    names.sort()
    return names


