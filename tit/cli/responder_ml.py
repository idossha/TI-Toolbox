#!/usr/bin/env simnibs_python
"""
Responder ML CLI.

Train a responder/non-responder classifier from TI_max E-field NIfTIs in MNI space
using the Glasser atlas in `resources/atlas/` by default.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Allow running as a standalone script (e.g. `simnibs_python responder_ml.py ...`)
# from within the `tit/cli/` folder by ensuring the repo root is importable.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tit.cli.base import ArgumentDefinition, BaseCLI


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
                name="task",
                type=str,
                choices=["classification", "regression"],
                help="Training task type. classification=0/1 target; regression=continuous target",
                default="classification",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="target_col",
                type=str,
                help="Name of target column in the CSV (default: response). For regression, use e.g. effect_size.",
                default="response",
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

    def execute(self, args: Dict[str, Any]) -> int:
        cmd = (args.get("command") or "").strip()
        csv_path = args.get("csv")
        model_path = args.get("model")

        if cmd == "train":
            from tit.cli import utils as cli_utils
            from tit.ml.responder.config import (
                ResponderMLConfig,
                default_subjects_csv_path,
            )
            from tit.ml.responder.train import train_from_csv

            if not csv_path:
                csv_path = str(default_subjects_csv_path())

            run_name = args.get("run_name") or cli_utils.now_compact()
            cfg = ResponderMLConfig(
                csv_path=Path(csv_path),
                task=str(args.get("task") or "classification"),
                target_col=str(args.get("target_col") or "response"),
                atlas_path=Path(args["atlas_path"]) if args.get("atlas_path") else None,
                atlas_labels_path=(
                    Path(args["atlas_labels_path"])
                    if args.get("atlas_labels_path")
                    else None
                ),
                run_name=str(run_name),
                output_dir=Path(args["output_dir"]) if args.get("output_dir") else None,
                outer_splits=int(args.get("outer_splits") or 5),
                inner_splits=int(args.get("inner_splits") or 4),
                random_state=int(args.get("seed") or 42),
                n_jobs=int(args.get("n_jobs") or 1),
                bootstrap_samples=int(args.get("bootstrap") or 0),
                verbose=bool(args.get("verbose") or False),
            )
            train_from_csv(cfg)
            return 0

        if cmd == "predict":
            if not model_path:
                raise RuntimeError("--model is required for predict")
            from tit.ml.responder.predict import predict_from_csv
            from tit.ml.responder.config import default_subjects_csv_path

            if not csv_path:
                csv_path = str(default_subjects_csv_path())

            out = Path(args["output_dir"]) if args.get("output_dir") else None
            predict_from_csv(
                model_path=Path(model_path),
                csv_path=Path(csv_path),
                output_csv=(out / "predictions.csv") if out else None,
            )
            return 0

        if cmd == "explain":
            if not model_path:
                raise RuntimeError("--model is required for explain")
            from tit.ml.responder.explain import explain_model

            explain_model(
                model_path=Path(model_path),
                output_dir=Path(args["output_dir"]) if args.get("output_dir") else None,
                atlas_path=Path(args["atlas_path"]) if args.get("atlas_path") else None,
                atlas_labels_path=(
                    Path(args["atlas_labels_path"])
                    if args.get("atlas_labels_path")
                    else None
                ),
            )
            return 0

        raise RuntimeError(f"Unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(ResponderMLCLI().run())
