"""Multipolar exhaustive-search engine."""

import logging
import signal
import time
from collections import deque

import numpy as np
from simnibs.utils import TI_utils as TI

from tit.calc import get_mTI_vectors
from tit.opt.ex.engine import ExSearchEngine
from tit.opt.ex.parallel import evaluate_ordered, resolve_n_jobs

from .logic import count_multipolar_combinations, generate_multipolar_combinations


class MExSearchEngine(ExSearchEngine):
    """Exhaustive search engine for four-pair (eight-electrode) mTI montages.

    Scores each candidate with the verified N>2 mTI envelope
    (:func:`tit.calc.get_mTI_vectors`), not a recursive envelope-of-envelopes
    dispatch -- that path is not the TI envelope for N>2 fields (see the
    ``get_mTI_vectors`` module docstring in ``tit/calc.py``).
    """

    def __init__(
        self,
        leadfield_hdf: str,
        roi_file: str | tuple[str, int] | list[str | tuple[str, int]],
        roi_name: str,
        logger: logging.Logger,
        channels: list[tuple[list[int], list[int]]] | None = None,
    ):
        super().__init__(leadfield_hdf, roi_file, roi_name, logger)
        self.channels = channels

    def compute_mti_field(
        self,
        electrodes: tuple[str, str, str, str, str, str, str, str],
        current_mA: float,
    ) -> dict[str, float]:
        """Compute one four-pair mTI candidate and return ROI metrics.

        The K>=2 envelope (:func:`tit.calc.get_mTI_vectors`) is a per-element
        direction search -- far costlier than the 2-pair closed form -- so it
        is evaluated only on ``ROI | GM`` (:meth:`_evaluation_subset`).
        """
        subset, roi_pos, gm_pos = self._evaluation_subset()
        fields = [
            TI.get_field(
                [electrodes[idx], electrodes[idx + 1], current_mA / 1000.0],
                self.leadfield,
                self.idx_lf,
            )[subset]
            for idx in range(0, 8, 2)
        ]

        vectors = get_mTI_vectors(fields, channels=self.channels)
        metric = np.linalg.norm(vectors, axis=1)

        data = self._roi_metrics(metric[roi_pos], metric[gm_pos])
        for ch in range(1, 5):
            data[f"current_ch{ch}_mA"] = current_mA
        return data

    def run(
        self,
        buckets_or_pool,
        all_combinations: bool,
        output_dir: str,
        current_mA: float,
        symmetry_mirror_map: dict[str, str] | None = None,
        symmetry_pairing: str = "within_pairs",
        n_jobs: int = 1,
    ) -> dict[str, dict[str, float]]:
        """Run the full multipolar search loop.

        Candidates are evaluated in enumeration order on ``n_jobs`` forked
        workers (``n_jobs < 1``: all cores minus one; ``1``: in-process).
        """
        stop = False

        def _on_signal(sig, frame):
            nonlocal stop
            stop = True

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        total = count_multipolar_combinations(
            buckets_or_pool,
            all_combinations=all_combinations,
            symmetry_mirror_map=symmetry_mirror_map,
            symmetry_pairing=symmetry_pairing,
            channels=self.channels,
        )
        self.logger.info("%s", "\n" + "=" * 60)
        mode = "All Combinations" if all_combinations else "Bucketed"
        if symmetry_mirror_map is not None:
            mode += f", left/right symmetric ({symmetry_pairing})"
        self.logger.info("Multipolar Exhaustive Search (%s)", mode)
        self.logger.info("Current per pair: %.3f mA", current_mA)
        self.logger.info("Channels: %s", self.channels or "consecutive pairing")
        self.logger.info("Total combinations: %d", total)
        n_jobs = resolve_n_jobs(n_jobs)
        self.logger.info("Workers: %d", n_jobs)
        self.logger.info("%s", "=" * 60 + "\n")

        results: dict[str, dict[str, float]] = {}
        start_time = time.time()

        candidates = generate_multipolar_combinations(
            buckets_or_pool,
            all_combinations=all_combinations,
            symmetry_mirror_map=symmetry_mirror_map,
            symmetry_pairing=symmetry_pairing,
            channels=self.channels,
        )
        # Two views of one generator: the pool consumes one lazily to feed
        # workers, the loop below pairs each result with its electrodes.
        pending: deque[tuple] = deque()

        def _feed():
            for electrodes in candidates:
                pending.append(electrodes)
                yield (electrodes, current_mA)

        evaluations = evaluate_ordered(
            self, "compute_mti_field", _feed(), n_jobs, n_tasks=total
        )

        i = 0
        for data in evaluations:
            i += 1
            electrodes = pending.popleft()
            sim_start = time.time()

            pair_names = [
                f"{electrodes[idx]}_{electrodes[idx + 1]}" for idx in range(0, 8, 2)
            ]
            name = "_and_".join(pair_names) + f"_I-{current_mA:.1f}mA"
            key = f"TI_field_{name}.msh"

            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0

            self.logger.info("[%d/%d] %s", i, total, name)
            if total:
                self.logger.info(
                    "  %.1f%% | %.2f/s | ETA %.1fmin",
                    100 * i / total,
                    rate,
                    eta / 60,
                )

            results[key] = data
            self.logger.info(
                "  Max=%.4f Mean=%.4f Foc=%.4f",
                data[f"{self.roi_name}_TImax_ROI"],
                data[f"{self.roi_name}_TImean_ROI"],
                data[f"{self.roi_name}_Focality"],
            )
            self._log_progress_estimate(i, total, start_time)
            if stop:
                self.logger.warning("Interrupted")
                evaluations.close()
                break

        if results:
            elapsed = time.time() - start_time
            self.logger.info(
                "Done: %d/%d in %.1fmin (%.2fs each)",
                len(results),
                total,
                elapsed / 60,
                elapsed / len(results),
            )
            self.logger.info("Output: %s", output_dir)

        return results

    def _log_progress_estimate(
        self,
        completed: int,
        total: int,
        start_time: float,
        interval: int = 500,
    ) -> None:
        """Log a coarse progress/ETA line every *interval* candidates.

        The combinatorial candidate count for four bucketed pairs (or pool
        permutations) can run into the hundreds of thousands, where a
        per-candidate log line (already emitted above) is too noisy to be
        useful for tracking overall progress.
        """
        if not total or completed <= 0:
            return
        if completed != total and completed % interval != 0:
            return

        elapsed = time.time() - start_time
        rate = completed / elapsed if elapsed > 0 else 0.0
        eta = (total - completed) / rate if rate > 0 else 0.0
        self.logger.info(
            "Progress estimate: %d/%d (%.1f%%) | elapsed %.1fmin | ETA %.1fmin | %.2f/s",
            completed,
            total,
            100 * completed / total,
            elapsed / 60,
            eta / 60,
            rate,
        )
