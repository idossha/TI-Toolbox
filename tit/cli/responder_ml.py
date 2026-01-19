#!/usr/bin/env simnibs_python
"""
Responder ML CLI.

Train a responder/non-responder classifier from TI_max E-field NIfTIs in MNI space
using the Glasser atlas in `resources/atlas/` by default.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Allow running as a standalone script (e.g. `simnibs_python responder_ml.py ...`)
# from within the `tit/cli/` folder by ensuring the repo root is importable.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tit.cli.base import ArgumentDefinition, BaseCLI
from tit import logger as logging_util


class ResponderMLCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__(
            "Responder prediction from TI_max NIfTIs (MNI, GM-masked) using atlas ROI features."
        )

        self.add_argument(
            ArgumentDefinition(
                name="command",
                type=str,
                choices=["train", "predict", "explain"],
                required=True,
                help="Which action to run: train|predict|explain",
            )
        )

        self.add_argument(
            ArgumentDefinition(
                name="csv", type=str, help="Path to subjects.csv", required=False
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="model", type=str, help="Path to model.joblib", required=False
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="target_col",
                type=str,
                help="Name of target column in the CSV (default: response).",
                default="response",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="task",
                type=str,
                choices=["classification", "regression"],
                help="ML task type (classification or regression).",
                default="classification",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="condition_col",
                type=str,
                help="Optional name of a condition column. Rows whose condition equals `sham_value` will be treated as sham and get all-zero ROI features (no NIfTI required).",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="sham_value",
                type=str,
                help="Value in condition_col that indicates sham (case-insensitive). Default: sham",
                default="sham",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="atlas_path",
                type=str,
                help="Atlas NIfTI path (default: Glasser)",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="atlas_labels_path",
                type=str,
                help="Atlas labels TSV path (optional; default: <atlas_basename>.tsv). Must be a .tsv with number/label columns (RGB optional).",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="run_name",
                type=str,
                help="Run name (train output folder name)",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="output_dir",
                type=str,
                help="Override output directory",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="outer_splits",
                type=int,
                help="Outer CV folds",
                default=5,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="inner_splits",
                type=int,
                help="Inner CV folds",
                default=4,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="seed", type=int, help="Random seed", default=42, required=False
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="n_jobs",
                type=int,
                help="Parallel jobs for sklearn",
                default=1,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="max_iter",
                type=int,
                help="Max iterations for LogisticRegression",
                default=10000,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="tol",
                type=float,
                help="Tolerance for LogisticRegression convergence",
                default=1e-4,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="verbose",
                type=bool,
                help="Verbose progress output",
                default=False,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="bootstrap",
                type=int,
                help="Bootstrap samples for coefficient stability (0 disables)",
                default=0,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="permutation_tests",
                type=int,
                help="Permutation tests for stability (0 disables)",
                default=0,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="feature_reduction_approach",
                type=str,
                choices=["atlas_roi", "stats_ttest", "stats_fregression"],
                help="Feature reduction approach: atlas_roi (traditional ROI averaging), stats_ttest (t-test voxel selection), or stats_fregression (F-test voxel selection for regression)",
                default="atlas_roi",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="ttest_threshold",
                type=float,
                help="P-value threshold for statistical feature selection (only used with stats_ttest approach)",
                default=0.001,
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="ttest_cv_feature_selection",
                type=bool,
                help="Perform feature selection within each CV fold (more robust but slower)",
                default=False,
                required=False,
            )
        )


    def execute(self, args: Dict[str, Any]) -> int:
        cmd = (args.get("command") or "").strip()
        csv_path = args.get("csv")
        model_path = args.get("model")

        if cmd == "train":
            from tit.cli import utils as cli_utils
            from tit.ml.responder.config import (
                ResponderMLConfig,
                default_subjects_csv_path,
                default_output_dir,
            )
            from tit.ml.responder.train import train_from_csv

            if not csv_path:
                csv_path = str(default_subjects_csv_path())

            run_name = args.get("run_name") or cli_utils.now_compact()
            out_dir = Path(args["output_dir"]) if args.get("output_dir") else None
            out_dir = out_dir or default_output_dir(run_name=str(run_name))
            out_dir.mkdir(parents=True, exist_ok=True)
            log_path = out_dir / "responder_ml.log"
            logger = logging_util.get_logger(
                "tit.cli.responder_ml.train",
                log_file=str(log_path),
                overwrite=True,
                console=True,
            )
            logger.info(f"Command line: {' '.join(sys.argv)}")
            try:
                logger.info(
                    "CLI args: %s",
                    json.dumps(args, indent=2, sort_keys=True),
                )
            except Exception:
                logger.info(f"CLI args (raw): {args}")
            cfg = ResponderMLConfig(
                csv_path=Path(csv_path),
                task=str(args.get("task") or "classification"),
                target_col=str(args.get("target_col") or "response"),
                condition_col=(
                    str(args.get("condition_col")).strip()
                    if args.get("condition_col")
                    else None
                ),
                sham_value=str(args.get("sham_value") or "sham"),
                atlas_path=Path(args["atlas_path"]) if args.get("atlas_path") else None,
                atlas_labels_path=(
                    Path(args["atlas_labels_path"])
                    if args.get("atlas_labels_path")
                    else None
                ),
                run_name=str(run_name),
                # Force output_dir so errors are always written to <out_dir>/responder_ml.log
                output_dir=out_dir,
                feature_reduction_approach=str(args.get("feature_reduction_approach") or "atlas_roi"),
                ttest_p_threshold=float(args.get("ttest_threshold") or 0.001),
                ttest_cv_feature_selection=bool(args.get("ttest_cv_feature_selection") or False),
                outer_splits=int(args.get("outer_splits") or 5),
                inner_splits=int(args.get("inner_splits") or 4),
                random_state=int(args.get("seed") or 42),
                n_jobs=int(args.get("n_jobs") or 1),
                max_iter=int(args.get("max_iter") or 10000),
                tol=float(args.get("tol") or 1e-4),
                bootstrap_samples=int(args.get("bootstrap") or 0),
                permutation_tests=int(args.get("permutation_tests") or 0),
                verbose=bool(args.get("verbose") or False),
            )
            try:
                train_from_csv(cfg)
            except Exception:
                logger.exception("Responder ML train failed.")
                raise
            return 0

        if cmd == "predict":
            if not model_path:
                raise RuntimeError("--model is required for predict")
            from tit.ml.responder.predict import predict_from_csv
            from tit.ml.responder.config import default_subjects_csv_path

            if not csv_path:
                csv_path = str(default_subjects_csv_path())

            out = Path(args["output_dir"]) if args.get("output_dir") else None
            out_csv = (out / "predictions.csv") if out else None
            log_dir = out if out else Path(model_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            logger = logging_util.get_logger(
                "tit.cli.responder_ml.predict",
                log_file=str(log_dir / "responder_ml.log"),
                overwrite=False,
                console=True,
            )
            try:
                predict_from_csv(
                    model_path=Path(model_path),
                    csv_path=Path(csv_path),
                    output_csv=out_csv,
                )
            except Exception:
                logger.exception("Responder ML predict failed.")
                raise
            return 0

        if cmd == "explain":
            if not model_path:
                raise RuntimeError("--model is required for explain")
            from tit.ml.responder.explain import explain_model

            out_dir = Path(args["output_dir"]) if args.get("output_dir") else None
            log_dir = out_dir if out_dir else Path(model_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            logger = logging_util.get_logger(
                "tit.cli.responder_ml.explain",
                log_file=str(log_dir / "responder_ml.log"),
                overwrite=False,
                console=True,
            )
            try:
                explain_model(
                    model_path=Path(model_path),
                    output_dir=out_dir,
                    atlas_path=Path(args["atlas_path"])
                    if args.get("atlas_path")
                    else None,
                    atlas_labels_path=(
                        Path(args["atlas_labels_path"])
                        if args.get("atlas_labels_path")
                        else None
                    ),
                )
            except Exception:
                logger.exception("Responder ML explain failed.")
                raise
            return 0

        raise RuntimeError(f"Unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(ResponderMLCLI().run())
