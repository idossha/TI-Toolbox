"""Generic MNE covariance, inverse and source-map operations.

Frequency bands, reference, noise definition and inverse parameters belong to
study configuration. These operations do not detect events or select outcomes.
"""

from __future__ import annotations

from collections.abc import Sequence

import mne
import numpy as np
from scipy import sparse


def subtract_intervals(
    intervals: Sequence[tuple[float, float]],
    exclusions: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Subtract the union of exclusions, preserving interval order and boundaries."""
    if any(
        not np.isfinite((start, end)).all() or end < start
        for start, end in (*intervals, *exclusions)
    ):
        raise ValueError("Intervals must have finite ordered endpoints")
    merged = []
    for start, end in sorted(exclusions):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    clean = []
    for start, end in intervals:
        cursor = start
        for left, right in merged:
            if right <= cursor or left >= end:
                continue
            if left > cursor:
                clean.append((cursor, min(left, end)))
            cursor = max(cursor, right)
        if cursor < end:
            clean.append((cursor, end))
    return clean


def epochs_from_intervals(
    raw: mne.io.BaseRaw,
    intervals: Sequence[tuple[float, float]],
    *,
    exclusions: Sequence[tuple[float, float]] = (),
    epoch_duration: float = 2.0,
    legacy_sampling: bool = False,
    reject_by_annotation: bool = True,
    picks: object = None,
) -> mne.Epochs:
    """Construct non-overlapping noise epochs from raw-relative second intervals.

    Modern sampling includes exactly fitting epochs and accounts for first_samp.
    ``legacy_sampling=True`` reproduces older analyses using truncated sample
    bounds, omitting exactly fitting terminal epochs and treating event samples
    as absolute without adding first_samp. This mode is for reproducibility only.
    Intervals are half-open; default bounds round inward to avoid excluded data.
    """
    sfreq = raw.info["sfreq"]
    if not np.isfinite(epoch_duration) or epoch_duration <= 0:
        raise ValueError("epoch_duration must be positive and finite")
    step = (
        int(epoch_duration * sfreq)
        if legacy_sampling
        else int(round(epoch_duration * sfreq))
    )
    if step < 1:
        raise ValueError("epoch_duration must span at least one sample")
    events = []
    for start_sec, end_sec in subtract_intervals(intervals, exclusions):
        start = max(
            0,
            (
                int(start_sec * sfreq)
                if legacy_sampling
                else int(np.ceil(start_sec * sfreq))
            ),
        )
        end = min(
            raw.n_times,
            int(end_sec * sfreq) if legacy_sampling else int(np.floor(end_sec * sfreq)),
        )
        stop = end - step if legacy_sampling else end - step + 1
        shift = 0 if legacy_sampling else raw.first_samp
        events.extend([sample + shift, 0, 1] for sample in range(start, stop, step))
    if not events:
        raise ValueError("No complete noise epochs remain in the requested intervals")
    # Keep the historical floating-duration tmax in compatibility mode.
    tmax = epoch_duration - 1 / sfreq if legacy_sampling else (step - 1) / sfreq
    return mne.Epochs(
        raw,
        np.asarray(events, dtype=int),
        event_id={"noise": 1},
        tmin=0.0,
        tmax=tmax,
        baseline=None,
        preload=True,
        picks=picks,
        reject_by_annotation=reject_by_annotation,
        verbose=False,
    )


def covariance_from_intervals(
    raw: mne.io.BaseRaw,
    intervals: Sequence[tuple[float, float]],
    *,
    exclusions: Sequence[tuple[float, float]] = (),
    epoch_duration: float = 2.0,
    method: str | Sequence[str] = "auto",
    rank: object = None,
    legacy_sampling: bool = False,
    reject_by_annotation: bool = True,
    picks: object = None,
) -> mne.Covariance:
    """Estimate MNE noise covariance from explicitly selected event-free intervals."""
    epochs = epochs_from_intervals(
        raw,
        intervals,
        exclusions=exclusions,
        epoch_duration=epoch_duration,
        legacy_sampling=legacy_sampling,
        reject_by_annotation=reject_by_annotation,
        picks=picks,
    )
    if len(epochs) == 0:
        raise ValueError("No noise epochs remain after annotation rejection")
    return mne.compute_covariance(epochs, method=method, rank=rank, verbose=False)


def prepare_inverse(
    info: mne.Info,
    forward: mne.Forward,
    covariance: mne.Covariance,
    *,
    loose: object,
    depth: object,
    rank: object = None,
) -> object:
    """Align forward channels and construct an inverse with caller-selected priors.

    The input Info must already carry its reference/projectors and bad channels.
    Frequency filtering and covariance selection are deliberately separate.
    """
    selected = mne.pick_channels_forward(forward, include=info.ch_names, ordered=True)
    return mne.minimum_norm.make_inverse_operator(
        info, selected, covariance, loose=loose, depth=depth, rank=rank, verbose=False
    )


def apply_inverse_windows(
    data: np.ndarray,
    info: mne.Info,
    inverse: object,
    peak_samples: np.ndarray,
    offsets: np.ndarray,
    *,
    lambda2: float,
    method: str,
    pick_ori: str | None = None,
    morph: object = None,
) -> np.ndarray:
    """Apply an inverse to a batch of event windows: vertex[, orientation], event, time.

    Sample indices are relative to ``data``. The caller defines and retains event
    identities/timing. The linear inverse and optional morph are batched through
    an EvokedArray without averaging events; scalar magnitude is handled by MNE
    before morphing, preserving the same operation order as apply_inverse_epochs.
    Input windows must already be in bounds. Chunking is controlled by the caller.
    """
    values = np.asarray(data)
    peaks = np.asarray(peak_samples)
    window = np.asarray(offsets)
    if values.ndim != 2 or values.shape[0] != len(info.ch_names):
        raise ValueError("data must be channels x samples in Info channel order")
    if peaks.ndim != 1 or window.ndim != 1 or not peaks.size or not window.size:
        raise ValueError("peak_samples and offsets must be nonempty 1D arrays")
    if peaks.dtype.kind not in "iu" or window.dtype.kind not in "iu":
        raise ValueError("peak_samples and offsets must contain integer sample indices")
    columns = peaks[:, None] + window[None, :]
    if columns.min() < 0 or columns.max() >= values.shape[1]:
        raise ValueError("Requested inverse window extends outside data")
    block = values[:, columns.ravel()].astype(np.float64, copy=False)
    evoked = mne.EvokedArray(block, info, tmin=0, verbose=False)
    stc = mne.minimum_norm.apply_inverse(
        evoked,
        inverse,
        lambda2=lambda2,
        method=method,
        pick_ori=pick_ori,
        verbose=False,
    )
    if morph is not None:
        stc = morph.apply(stc, verbose=False)
    return stc.data.reshape(*stc.data.shape[:-1], len(peaks), len(window))


def diffusion_smoother(adjacency: sparse.spmatrix, n_iters: int) -> sparse.spmatrix:
    """Return n vertex-and-neighbor averaging steps on an explicit adjacency graph.

    Adds a self-edge exactly once to the supplied graph; pass a zero-diagonal
    adjacency to obtain equal weights for the vertex and each neighbor.
    """
    if (
        not sparse.issparse(adjacency)
        or adjacency.ndim != 2
        or adjacency.shape[0] != adjacency.shape[1]
    ):
        raise ValueError("adjacency must be square")
    if not isinstance(n_iters, (int, np.integer)) or n_iters < 0:
        raise ValueError("n_iters must be a nonnegative integer")
    if np.any(~np.isfinite(adjacency.data)) or np.any(adjacency.data < 0):
        raise ValueError("adjacency weights must be finite and nonnegative")
    n_vertices = adjacency.shape[0]
    with_self = adjacency + sparse.eye(n_vertices)
    degree = np.asarray(with_self.sum(axis=1)).ravel()
    transition = sparse.diags(1 / np.maximum(degree, 1)) @ with_self
    smoother = sparse.eye(n_vertices)
    for _ in range(n_iters):
        smoother = smoother @ transition
    return smoother
