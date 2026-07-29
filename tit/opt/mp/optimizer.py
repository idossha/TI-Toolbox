"""Scipy differential evolution wrapper for discrete electrode search.

Searches over electrode indices from the leadfield, using continuous DE
with rounding + a repair operator to ensure valid unique electrodes.
"""

import logging
import time

import numpy as np
from scipy.optimize import differential_evolution

from tit.opt.fast_eval import FastTIEvaluator

log = logging.getLogger(__name__)


def _repair_duplicates(indices: np.ndarray, n_elec: int) -> np.ndarray:
    """Replace duplicate electrode indices with nearest unused ones.

    Scans left-to-right; when a duplicate is found, assigns the closest
    unused index (searching outward from the duplicate value).
    """
    used = set()
    result = indices.copy()
    for i in range(len(result)):
        if result[i] not in used:
            used.add(result[i])
            continue
        # Find nearest unused index
        for offset in range(1, n_elec):
            for candidate in (result[i] + offset, result[i] - offset):
                if 0 <= candidate < n_elec and candidate not in used:
                    result[i] = candidate
                    used.add(candidate)
                    break
            else:
                continue
            break
    return result


def _parse_mutation(mutation_str: str | None) -> float | list[float]:
    """Parse mutation parameter from string to float or list of floats."""
    if mutation_str is None:
        return (0.5, 1.0)
    mutation_str = mutation_str.strip()
    if "," in mutation_str:
        return [float(x.strip()) for x in mutation_str.split(",")]
    return float(mutation_str)


def run_de_search(
    evaluator: FastTIEvaluator,
    valid_electrodes: list[tuple[str, int]],
    config,
    logger: logging.Logger,
) -> dict:
    """Run differential evolution over discrete electrode indices.

    Parameters
    ----------
    evaluator : FastTIEvaluator
        Configured evaluator with ROI/non-ROI already set up.
    valid_electrodes : list of (name, leadfield_index) tuples
        Valid electrode positions from the leadfield.
    config : MultiPolarConfig
        Search configuration.
    logger : logging.Logger
        Logger for progress output.

    Returns
    -------
    dict with best_focality, best_montage, best_indices, n_iterations,
    n_evaluations, convergence_success, message
    """
    n_elec = len(valid_electrodes)
    n_dims = 2 * config.n_pairs
    names = [e[0] for e in valid_electrodes]
    lf_indices = [e[1] for e in valid_electrodes]

    if n_elec < n_dims:
        raise ValueError(
            f"Need at least {n_dims} valid electrodes for {config.n_pairs} pairs, "
            f"got {n_elec}"
        )

    bounds = [(0, n_elec - 1)] * n_dims
    current_A = config.current_mA / 1000.0
    currents_A = np.full(config.n_pairs, current_A)

    # N>2 envelope grouping scheme (finding F11) -- psi only applies to
    # "multiband", where it is the frequency plan's per-interference-pair
    # envelope phase offset. "dual_carrier" collapses to K=1 and has no
    # per-pair phase to give it.
    scheme = config.scheme
    psi = (
        config.frequency_plan.psi
        if scheme == "multiband" and config.frequency_plan is not None
        else None
    )

    # DE parameters
    maxiter = config.max_iterations if config.max_iterations is not None else 500
    popsize = config.population_size if config.population_size is not None else 30
    tol = config.tolerance if config.tolerance is not None else 0.01
    mutation = _parse_mutation(config.mutation)
    recombination = config.recombination if config.recombination is not None else 0.7

    # Evaluation counter
    n_evals = [0]

    # Finding F10, real-leadfield follow-up. Two independent search-time
    # speedups, profiled on a real 74-electrode leadfield:
    #
    # 1. If a search subsample is configured, build pair diffs directly
    #    from the pre-sliced leadfield (precompute_pair_diffs_search)
    #    instead of the full mesh (precompute_pair_diffs) -- avoids a
    #    full-mesh (M, 3) allocation+subtraction per pair per candidate.
    #    Measured: real for K=1 (2 electrode pairs), negligible for K>=2.
    # 2. search_refine controls tit.calc.mti_modulation_depth's `refine`
    #    argument for K>=2 (n_pairs >= 4) candidates -- irrelevant for
    #    n_pairs=2, which never reaches mti_modulation_depth. Profiling
    #    found this, not (1), is the dominant K>=2 search-time cost (~95%
    #    of a K=2 evaluation). See tit/opt/fast_eval.py's module docstring
    #    and MultiPolarConfig.search_refine for the measured breakdown.
    #
    # Neither affects the final rescore below, which always uses the
    # full-mesh precompute_pair_diffs and evaluate_final's accurate
    # (refine=True) default.
    use_search_slice = evaluator.has_search_subsample
    search_refine = config.search_refine

    def objective(x):
        indices = np.clip(np.round(x).astype(int), 0, n_elec - 1)
        indices = _repair_duplicates(indices, n_elec)

        pairs = [
            (lf_indices[indices[2 * i]], lf_indices[indices[2 * i + 1]])
            for i in range(config.n_pairs)
        ]
        if use_search_slice:
            pair_diffs = evaluator.precompute_pair_diffs_search(pairs)
            focality = evaluator.focality_from_diffs(
                pair_diffs,
                currents_A,
                scheme=scheme,
                psi=psi,
                pre_sliced=True,
                refine=search_refine,
            )
        else:
            pair_diffs = evaluator.precompute_pair_diffs(pairs)
            focality = evaluator.focality_from_diffs(
                pair_diffs,
                currents_A,
                scheme=scheme,
                psi=psi,
                refine=search_refine,
            )
        n_evals[0] += 1
        return -focality

    # Multi-start loop
    best_result = None
    best_fval = float("inf")

    for start_i in range(config.n_multistart):
        if config.n_multistart > 1:
            logger.info(f"Multi-start run {start_i + 1}/{config.n_multistart}")

        # Progress callback
        iter_count = [0]
        stall_count = [0]
        prev_best = [float("inf")]
        t_start = time.time()

        def callback(xk, convergence=0):
            iter_count[0] += 1
            current_best = objective(xk)

            if iter_count[0] % 50 == 0 or iter_count[0] == 1:
                elapsed = time.time() - t_start
                logger.info(
                    f"  iter {iter_count[0]:>4d} | "
                    f"best_focality={-current_best:.4f} | "
                    f"convergence={convergence:.4f} | "
                    f"elapsed={elapsed:.1f}s"
                )

            # Early stopping via patience
            if current_best < prev_best[0] - 1e-8:
                prev_best[0] = current_best
                stall_count[0] = 0
            else:
                stall_count[0] += 1

            if config.patience and stall_count[0] >= config.patience:
                logger.info(
                    f"  Early stop: no improvement for {config.patience} generations"
                )
                return True

            return False

        result = differential_evolution(
            objective,
            bounds=bounds,
            maxiter=maxiter,
            popsize=popsize,
            tol=tol,
            mutation=mutation,
            recombination=recombination,
            seed=None,
            callback=callback,
            workers=1,
            updating="deferred",
        )

        if result.fun < best_fval:
            best_fval = result.fun
            best_result = result
            best_start = start_i

    # Decode best result
    best_x = np.clip(np.round(best_result.x).astype(int), 0, n_elec - 1)
    best_x = _repair_duplicates(best_x, n_elec)

    best_montage = []
    for i in range(config.n_pairs):
        plus_idx = best_x[2 * i]
        minus_idx = best_x[2 * i + 1]
        best_montage.append((names[plus_idx], names[minus_idx], config.current_mA))

    # Rescore the winning montage on the FULL mesh (finding F10): search may
    # have used a non-ROI subsample (setup_search_subsample), so -best_fval
    # is a search-time estimate, not the exact number to report.
    final_pairs = [
        (lf_indices[best_x[2 * i]], lf_indices[best_x[2 * i + 1]])
        for i in range(config.n_pairs)
    ]
    final_diffs = evaluator.precompute_pair_diffs(final_pairs)
    final_metrics = evaluator.evaluate_final(
        final_diffs, currents_A, scheme=scheme, psi=psi
    )
    best_focality = final_metrics["focality"]

    logger.info(
        f"DE complete: best_focality={best_focality:.4f} "
        f"(search estimate was {-best_fval:.4f})"
    )
    for plus_name, minus_name, mA in best_montage:
        logger.info(f"  {plus_name} -> {minus_name}  ({mA:.1f} mA)")

    return {
        "best_focality": best_focality,
        "best_montage": best_montage,
        "best_indices": best_x.tolist(),
        "n_iterations": best_result.nit,
        "n_evaluations": n_evals[0],
        "convergence_success": best_result.success,
        "message": best_result.message,
        "final_metrics": final_metrics,
        "search_focality_estimate": -best_fval,
    }
