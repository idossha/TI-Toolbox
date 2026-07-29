#!/usr/bin/env simnibs_python
"""Ground-truth verification harness for ``tit.calc.mti_modulation_depth``.

Synthesises the multi-carrier waveform a set of mTI electrode pairs would
produce at a point, in the time domain, then demodulates it with
Botzanowski et al.'s chain (square -> brick-wall low-pass -> sqrt) to get
an independent, closed-form-free ground truth for the envelope amplitude.
Compares that ground truth against ``mti_modulation_depth()``'s coherent
closed form.

This is the ground-truth harness referenced by
``tracks/active/mti-focality-core.md`` (Phase 1, findings F1-F3) and
mirrored (with tighter, pytest-friendly parameters) in
``tests/test_calc_mti.py``. Run it directly for a human-readable
pass/fail report -- it must be run where ``tit`` is importable, e.g.
inside the SimNIBS container::

    simnibs_python scripts/verify_mti_envelope.py
    simnibs_python scripts/verify_mti_envelope.py --k 1 2 4 6 8 --trials 20 --verbose

Exit code is 0 if every check passes, 1 otherwise.
"""

import argparse
import sys
from dataclasses import dataclass

import numpy as np

from tit.calc import (
    compute_botzanowski_directional_am_stats,
    get_TI_vectors,
    mti_modulation_depth,
)

# ---------------------------------------------------------------------------
# Time-domain ground truth
# ---------------------------------------------------------------------------


def demodulate(x: np.ndarray, fs: float, lp_hz: float = 200.0) -> np.ndarray:
    """Botzanowski chain: square -> zero-phase brick-wall low-pass -> sqrt.

    Returns the RMS envelope. The brick-wall low-pass is applied in the
    frequency domain (zeroing bins above *lp_hz*) so the comparison is not
    contaminated by a particular filter's transition-band ringing.
    """
    x2 = x**2
    X = np.fft.rfft(x2)
    freqs = np.fft.rfftfreq(len(x2), 1.0 / fs)
    X[freqs > lp_hz] = 0.0
    lp = np.fft.irfft(X, n=len(x2))
    return np.sqrt(np.maximum(lp, 0.0))


def ground_truth_md(
    a,
    b,
    fca,
    fcb,
    pha,
    phb,
    fs: float = 200_000.0,
    dur: float = 0.4,
    edge: float = 0.05,
) -> float:
    """Synthesise the projected multi-carrier waveform, demodulate, return peak MD.

    Parameters
    ----------
    a, b : array-like, shape (K,)
        Signed per-pair sub-channel amplitudes (already projected onto the
        direction of interest).
    fca, fcb : array-like, shape (K,)
        Carrier frequencies (Hz) for sub-channels a and b, one per pair.
    pha, phb : array-like, shape (K,)
        Hardware phase offsets (radians) for sub-channels a and b.
    fs : float
        Sample rate (Hz). Must be well above 2x the highest carrier.
    dur : float
        Signal duration (s).
    edge : float
        Fraction of samples dropped from each end before taking max/min,
        to avoid FFT edge effects.
    """
    t = np.arange(0, dur, 1.0 / fs)
    x = np.zeros_like(t)
    for ak, bk, fa, fb, pa, pb in zip(a, b, fca, fcb, pha, phb):
        x += ak * np.cos(2 * np.pi * fa * t + pa)
        x += bk * np.cos(2 * np.pi * fb * t + pb)
    env_rms = demodulate(x, fs, lp_hz=200.0)
    n_edge = int(edge * len(t))
    core = env_rms[n_edge:-n_edge]
    return float(np.sqrt(2.0) * (core.max() - core.min()))


def make_fields(a, b):
    """Embed scalar per-pair amplitudes as (1, 3) field arrays aligned with
    the x-axis, so that projecting onto direction=[1,0,0] recovers a, b
    exactly (isolates the closed-form math from direction-sweep sampling)."""
    fields = []
    for ak, bk in zip(a, b):
        fields.append(np.array([[float(ak), 0.0, 0.0]]))
        fields.append(np.array([[float(bk), 0.0, 0.0]]))
    return fields


_UNIT_X = np.array([[1.0, 0.0, 0.0]])


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    worst_metric: float = float("nan")
    tol: float = float("nan")


def check_ground_truth(
    k_values, n_trials, tol_pct, rng, phase_aware, verbose
) -> CheckResult:
    """K in k_values, psi=None or random psi, vs time-domain ground truth."""
    label = "random psi" if phase_aware else "psi=None"
    worst = 0.0
    n_checked = 0
    for K in k_values:
        means = np.linspace(2000.0, 2000.0 + 2000.0 * (K - 1), K)
        df = 50.0
        for trial in range(n_trials):
            a = rng.normal(size=K) * 1.5
            b = rng.normal(size=K) * 1.5
            pha = np.zeros(K)
            phb = rng.uniform(0, 2 * np.pi, K) if phase_aware else np.zeros(K)
            psi = (phb - pha) if phase_aware else None

            gt = ground_truth_md(a, b, means - df / 2, means + df / 2, pha, phb)
            res = mti_modulation_depth(make_fields(a, b), psi=psi, directions=_UNIT_X)
            err_pct = 100 * abs(res["md"][0] - gt) / max(gt, 1e-12)
            worst = max(worst, err_pct)
            n_checked += 1
            if verbose:
                print(
                    f"    K={K} trial={trial} ({label}): truth={gt:.6f} formula={res['md'][0]:.6f} err={err_pct:.5f}%"
                )

    passed = worst < tol_pct
    return CheckResult(
        name=f"Ground truth vs closed form ({label}, K={list(k_values)}, n={n_checked})",
        passed=passed,
        detail=f"worst error {worst:.5f}% over {n_checked} trials (tol {tol_pct}%)",
        worst_metric=worst,
        tol=tol_pct,
    )


def check_k1_exact_reduction(n_trials, rng, verbose) -> CheckResult:
    """K=1 reduces EXACTLY (< 1e-9) to 2*min(|a|,|b|)."""
    worst = 0.0
    for _ in range(n_trials):
        a, b = rng.normal(size=2) * 3
        res = mti_modulation_depth(make_fields([a], [b]), directions=_UNIT_X)
        want = 2 * min(abs(a), abs(b))
        diff = abs(res["md"][0] - want)
        worst = max(worst, diff)
        if verbose:
            print(
                f"    a={a:+.4f} b={b:+.4f} formula={res['md'][0]:.9f} 2min={want:.9f} diff={diff:.2e}"
            )
    passed = worst < 1e-9
    return CheckResult(
        name=f"K=1 exact reduction to 2*min(|a|,|b|) (n={n_trials})",
        passed=passed,
        detail=f"worst abs diff {worst:.2e} (tol 1e-9)",
        worst_metric=worst,
        tol=1e-9,
    )


def check_anti_phase(verbose) -> CheckResult:
    """K=2, equal amplitudes, psi=[0, pi] -> aggregate envelope is exactly 0."""
    fields = make_fields([1.0, 1.0], [1.0, 1.0])
    psi = np.array([0.0, np.pi])
    res = mti_modulation_depth(fields, psi=psi, directions=_UNIT_X)
    md = res["md"][0]
    if verbose:
        print(f"    anti-phase K=2, equal amplitudes: md={md:.2e} (expect ~0)")
    passed = abs(md) < 1e-9
    return CheckResult(
        name="Anti-phase cancellation (K=2, psi=[0,pi] -> MD=0)",
        passed=passed,
        detail=f"md={md:.2e} (tol 1e-9)",
        worst_metric=abs(md),
        tol=1e-9,
    )


def check_psi_none_matches_ported(n_trials, rng, verbose) -> CheckResult:
    """psi=None AND refine=False reproduces the ported collaborator
    implementation (compute_botzanowski_directional_am_stats, from
    alba/ex-search-multipolar) to floating-point equality.

    refine=False is required as of the mti-carrier-metrics track: the
    default refine=True deliberately improves on the coarse-sweep-only
    result the ported implementation computes (K=1 exact closed form;
    K>=2 local refinement), so it is no longer expected to match
    bit-for-bit. refine=False is kept exactly for this kind of bit-parity
    check."""
    worst = 0.0
    for K in (1, 2, 4, 6):
        fields = [rng.normal(size=(30, 3)) for _ in range(2 * K)]
        ours = mti_modulation_depth(fields, refine=False)["md"]
        theirs = np.linalg.norm(
            compute_botzanowski_directional_am_stats(fields)["vectors"], axis=1
        )
        rel_err = np.max(np.abs(ours - theirs) / np.maximum(np.abs(theirs), 1e-12))
        worst = max(worst, rel_err)
        if verbose:
            print(
                f"    K={K}: max relative diff vs ported implementation = {rel_err:.2e}"
            )
    passed = worst < 1e-9
    return CheckResult(
        name="psi=None matches ported collaborator implementation (alba/ex-search-multipolar)",
        passed=passed,
        detail=f"worst relative diff {worst:.2e} (tol 1e-9)",
        worst_metric=worst,
        tol=1e-9,
    )


def check_k1_vs_closed_form_3d(n_trials, num_directions, rng, verbose) -> CheckResult:
    """K=1 best-direction sweep (refine=False) matches the exact Grossman
    closed form (get_TI_vectors) to < 0.1% in full 3D -- residual is
    direction-sweep sampling error, which shrinks as num_directions grows.
    This uses a much finer sweep than the 192-direction production default
    to demonstrate the closed form itself (not the coarse default sweep)
    is correct. (With the mti-carrier-metrics track's default refine=True,
    K=1 bypasses the sweep for the exact closed form directly -- see
    tests/test_calc_mti.py::TestK1ExactPath for that path's own check.)"""
    E1 = rng.normal(size=(n_trials, 3))
    E2 = rng.normal(size=(n_trials, 3))
    res = mti_modulation_depth([E1, E2], num_directions=num_directions, refine=False)
    md_sweep = res["md"]
    md_exact = np.linalg.norm(get_TI_vectors(E1, E2), axis=1)
    err_pct = 100 * np.abs(md_sweep - md_exact) / md_exact
    if verbose:
        for i, e in enumerate(err_pct):
            print(
                f"    trial {i}: sweep={md_sweep[i]:.6f} exact={md_exact[i]:.6f} err={e:.4f}%"
            )
    passed = err_pct.max() < 0.1
    return CheckResult(
        name=f"K=1 sweep (num_directions={num_directions}) vs exact closed form, full 3D",
        passed=passed,
        detail=f"worst error {err_pct.max():.4f}% over {n_trials} trials (tol 0.1%)",
        worst_metric=err_pct.max(),
        tol=0.1,
    )


def check_band_separation_sweep(f_cutoff, verbose) -> CheckResult:
    """Sweep the gap between two pairs' mean carrier frequencies and show
    the closed form's error grows as the gap - delta_f approaches
    f_cutoff (finding F7) -- informational, not a hard pass/fail gate, but
    flags a regression if the formula is suddenly wrong even at a
    comfortably large gap."""
    rng = np.random.default_rng(7)
    a = np.array([1.3, 0.9])
    b = np.array([1.1, 1.4])
    df = 50.0
    gaps = [25, 50, 100, 200, 400, 800, 1000, 2000]
    rows = []
    for gap in gaps:
        means = np.array([2000.0, 2000.0 + gap])
        gt = ground_truth_md(
            a, b, means - df / 2, means + df / 2, np.zeros(2), np.zeros(2)
        )
        res = mti_modulation_depth(make_fields(a, b), directions=_UNIT_X)
        err_pct = 100 * abs(res["md"][0] - gt) / gt
        margin = gap - df
        rows.append((gap, margin, gt, res["md"][0], err_pct))
        if verbose:
            valid = "valid" if margin > f_cutoff else "INVALID region"
            print(
                f"    gap={gap:5.0f}Hz margin={margin:6.0f}Hz ({valid}): truth={gt:.5f} formula={res['md'][0]:.5f} err={err_pct:.3f}%"
            )

    # Sanity gate: at the largest, clearly-valid gap the formula must be accurate.
    largest_gap_err = rows[-1][4]
    passed = largest_gap_err < 0.1
    return CheckResult(
        name="Band-separation sweep (F7 validity condition, informational)",
        passed=passed,
        detail=f"error at largest tested gap ({gaps[-1]} Hz) = {largest_gap_err:.4f}% (tol 0.1%)",
        worst_metric=largest_gap_err,
        tol=0.1,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_report(results: list[CheckResult]) -> bool:
    name_width = max(len(r.name) for r in results)
    print()
    print("=" * (name_width + 24))
    print("mTI envelope verification report")
    print("=" * (name_width + 24))
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name:<{name_width}}  {r.detail}")
    print("=" * (name_width + 24))
    n_pass = sum(r.passed for r in results)
    print(f"  {n_pass}/{len(results)} checks passed")
    print("=" * (name_width + 24))
    return all(r.passed for r in results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify tit.calc.mti_modulation_depth against a time-domain "
            "ground truth (Botzanowski square -> low-pass -> sqrt demodulator)."
        )
    )
    parser.add_argument(
        "--k",
        type=int,
        nargs="+",
        default=[1, 2, 4, 6],
        help="Electrode pair counts to test (default: 1 2 4 6)",
    )
    parser.add_argument(
        "--trials", type=int, default=5, help="Trials per K value (default: 5)"
    )
    parser.add_argument(
        "--seed", type=int, default=20260728, help="RNG seed (default: 20260728)"
    )
    parser.add_argument(
        "--tol-pct",
        type=float,
        default=0.01,
        help="Ground-truth agreement tolerance, percent (default: 0.01)",
    )
    parser.add_argument(
        "--num-directions",
        type=int,
        default=300_000,
        help="Direction-sweep resolution for the K=1-vs-closed-form-3D check (default: 300000)",
    )
    parser.add_argument(
        "--f-cutoff",
        type=float,
        default=200.0,
        help="Demodulation low-pass cutoff for the band-separation sweep (Hz)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print every trial, not just the summary"
    )
    args = parser.parse_args(argv)

    rng = np.random.default_rng(args.seed)

    results = [
        check_k1_exact_reduction(args.trials * 4, rng, args.verbose),
        check_ground_truth(
            args.k,
            args.trials,
            args.tol_pct,
            rng,
            phase_aware=False,
            verbose=args.verbose,
        ),
        check_ground_truth(
            args.k,
            args.trials,
            args.tol_pct,
            rng,
            phase_aware=True,
            verbose=args.verbose,
        ),
        check_anti_phase(args.verbose),
        check_psi_none_matches_ported(args.trials, rng, args.verbose),
        check_k1_vs_closed_form_3d(
            max(args.trials, 8), args.num_directions, rng, args.verbose
        ),
        check_band_separation_sweep(args.f_cutoff, args.verbose),
    ]

    all_passed = _print_report(results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
