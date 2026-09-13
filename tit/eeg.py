"""MNE-preserving EEG channel, annotation and interval utilities.

These helpers accept recording metadata and study-defined choices; no EEG cap,
stimulation duration, frequency band or condition names are selected implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from collections.abc import Sequence

import mne
import numpy as np


def harmonize_channels(
    raw: mne.io.BaseRaw,
    target_channels: Sequence[str],
    montage: str | mne.channels.DigMontage,
    *,
    exclude: Sequence[str] = (),
    preserve_bads: bool = True,
    copy: bool = True,
) -> mne.io.BaseRaw:
    """Interpolate missing EEG channels and return the requested channel order.

    Existing bad channels are included in interpolation by default. Set
    ``preserve_bads=False`` only to reproduce an analysis that interpolated newly
    absent channels alone. Input annotations, first sample and non-EEG metadata
    are retained; channels outside ``target_channels`` are removed explicitly.
    The supplied montage is applied only when interpolation is necessary.
    """
    names = list(target_channels)
    if not names or len(set(names)) != len(names):
        raise ValueError("target_channels must be a nonempty sequence of unique names")
    if set(names) & set(exclude):
        raise ValueError("target channels must not also be excluded")
    result = raw.copy() if copy else raw
    drops = [name for name in result.ch_names if name in exclude]
    if drops:
        result.drop_channels(drops)
    missing = [name for name in names if name not in result.ch_names]
    existing_bads = [name for name in result.info["bads"] if name in names]
    interpolate = missing or (preserve_bads and existing_bads)
    if interpolate:
        dig = (
            mne.channels.make_standard_montage(montage)
            if isinstance(montage, str)
            else montage
        )
        positions = dig.get_positions()["ch_pos"]
        absent = [name for name in names if name not in positions]
        if absent:
            raise ValueError(f"Montage has no positions for target channels: {absent}")
        result.set_montage(dig, on_missing="ignore")
        if missing:
            info = mne.create_info(missing, result.info["sfreq"], ch_types="eeg")
            added = mne.io.RawArray(
                np.zeros((len(missing), result.n_times)),
                info,
                first_samp=result.first_samp,
                verbose=False,
            )
            added.set_montage(dig, on_missing="raise")
            result.add_channels([added], force_update_info=True)
        result.info["bads"] = (
            list(dict.fromkeys(existing_bads + missing)) if preserve_bads else missing
        )
        result.interpolate_bads(reset_bads=True, verbose=False)
    result.reorder_channels(names)
    return result


def annotation_pairs(
    raw: mne.io.BaseRaw,
    start_marker: str,
    end_marker: str,
    *,
    min_duration: float = 0.0,
    max_duration: float = float("inf"),
    relative_to_raw: bool = True,
) -> list[tuple[float, float]]:
    """Pair normalized annotation labels, returning start/end times in seconds.

    Times are relative to the first stored sample by default. The legacy option
    ``relative_to_raw=False`` returns MNE annotation onsets unchanged. Pairing
    uses the first subsequent end marker; invalid-duration pairs are omitted.
    """
    if min_duration < 0 or max_duration < min_duration:
        raise ValueError("Require 0 <= min_duration <= max_duration")

    def normalize(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(text).lower())

    start_label, end_label = normalize(start_marker), normalize(end_marker)
    if not start_label or not end_label or start_label == end_label:
        raise ValueError("Start and end markers must be distinct nonempty labels")
    shift = raw.first_time if relative_to_raw else 0.0
    starts = sorted(
        float(a["onset"]) - shift
        for a in raw.annotations
        if normalize(a["description"]) == start_label
    )
    ends = sorted(
        float(a["onset"]) - shift
        for a in raw.annotations
        if normalize(a["description"]) == end_label
    )
    pairs = []
    end_idx = 0
    for start in starts:
        while end_idx < len(ends) and ends[end_idx] <= start:
            end_idx += 1
        if end_idx < len(ends):
            end = ends[end_idx]
            if min_duration <= end - start <= max_duration:
                pairs.append((start, end))
                end_idx += 1
    return pairs


@dataclass(frozen=True)
class StimulationWindow:
    """One stimulation interval and its explicitly constructed comparison windows."""

    protocol_idx: int
    stim_start_sec: float
    stim_end_sec: float
    pre_start_sec: float
    pre_end_sec: float
    post_start_sec: float
    post_end_sec: float


def stimulation_windows(
    pairs: Sequence[tuple[float, float]],
    *,
    pre_duration: float | None = None,
    post_duration: float | None = None,
    split_overlaps: bool = True,
) -> list[StimulationWindow]:
    """Construct comparison windows; None uses each stimulation interval's length.

    With ``split_overlaps=True``, adjacent POST/PRE overlaps are split at their
    midpoint. Intervals are not clipped to a recording; callers must explicitly
    decide recording boundaries and treatment of excluded/discontinuous time.
    """
    if any(end <= start for start, end in pairs):
        raise ValueError("Stimulation intervals must have positive duration")
    if any(pairs[i][0] > pairs[i + 1][0] for i in range(len(pairs) - 1)):
        raise ValueError("Stimulation intervals must be ordered by start time")
    if any(value is not None and value < 0 for value in (pre_duration, post_duration)):
        raise ValueError("Comparison durations must be nonnegative")
    result = []
    for i, (start, end) in enumerate(pairs):
        duration = end - start
        result.append(
            StimulationWindow(
                i,
                start,
                end,
                start - (duration if pre_duration is None else pre_duration),
                start,
                end,
                end + (duration if post_duration is None else post_duration),
            )
        )
    if split_overlaps:
        for i in range(len(result) - 1):
            current, following = result[i], result[i + 1]
            overlap = current.post_end_sec - following.pre_start_sec
            if overlap > 0:
                result[i] = replace(
                    current, post_end_sec=current.post_end_sec - overlap / 2
                )
                result[i + 1] = replace(
                    following, pre_start_sec=following.pre_start_sec + overlap / 2
                )
    return result


def sensor_adjacency(
    info: mne.Info,
    channel_names: Sequence[str] | None = None,
) -> tuple[object, list[str], list[int]]:
    """Return EEG adjacency with an explicit permutation of the input channel axis.

    ``info`` must already carry the caller's intended montage. The returned
    indices reorder ``channel_names`` (or info's names) into adjacency order.
    """
    names = list(info.ch_names if channel_names is None else channel_names)
    if len(set(names)) != len(names):
        raise ValueError("channel_names must be unique")
    if any(name not in info.ch_names for name in names):
        raise ValueError("All requested channels must be present in info")
    selected = mne.pick_info(
        info, mne.pick_channels(info.ch_names, names, ordered=True)
    )
    adjacency, ordered = mne.channels.find_ch_adjacency(selected, ch_type="eeg")
    return adjacency, ordered, [names.index(name) for name in ordered]
