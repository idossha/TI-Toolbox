from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import joblib
import sklearn

from tit.cli import utils as cli_utils

from .config import DEFAULT_EFIELD_FILENAME_PATTERN
from .dataset import load_efield_images, load_subject_table
from .features import extract_roi_features_from_efield


@dataclass(frozen=True)
class PredictArtifacts:
    output_csv: Path


def predict_from_csv(
    *,
    model_path: Path,
    csv_path: Path,
    output_csv: Optional[Path] = None,
) -> PredictArtifacts:
    """
    Predict for subjects in a CSV using a trained model bundle.

    The target column is optional at prediction time.
    - For classification models: writes probability (`proba`)
    - For regression models: writes continuous prediction (`pred`)
    """
    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")

    bundle = joblib.load(model_path)
    est = bundle.get("model")
    atlas_path = bundle.get("atlas_path")
    feature_names = list(bundle.get("feature_names") or [])
    cfg: Dict[str, Any] = dict(bundle.get("config") or {})
    task = str(cfg.get("task") or "classification")
    target_col = str(cfg.get("target_col") or "response")
    efield_filename_pattern = str(
        cfg.get("efield_filename_pattern") or DEFAULT_EFIELD_FILENAME_PATTERN
    )

    subjects = load_subject_table(
        csv_path,
        task=("regression" if task == "regression" else "classification"),
        target_col=target_col,
        require_target=False,
    )
    imgs, y, kept = load_efield_images(
        subjects, efield_filename_pattern=efield_filename_pattern
    )

    fm = extract_roi_features_from_efield(
        imgs, atlas_path=Path(atlas_path) if atlas_path else None
    )
    X = fm.X
    if feature_names and fm.feature_names != feature_names:
        raise RuntimeError(
            "Feature ordering mismatch between model bundle and newly extracted features. "
            "Ensure the same atlas and feature definition are used."
        )

    out = output_csv or (model_path.parent / "predictions.csv")
    if task == "regression":
        pred = np.asarray(est.predict(X), dtype=float)
        lines = [f"subject_id,simulation_name,{target_col},pred"]
        for s, yy, pp in zip(kept, y, pred.tolist()):
            tgt = "" if yy is None else float(yy)
            lines.append(f"{s.subject_id},{s.simulation_name},{tgt},{float(pp)}")
    else:
        proba = est.predict_proba(X)[:, 1]
        lines = [f"subject_id,simulation_name,{target_col},proba"]
        for s, yy, pp in zip(kept, y, proba.tolist()):
            tgt = "" if yy is None else int(float(yy))
            lines.append(f"{s.subject_id},{s.simulation_name},{tgt},{float(pp)}")
    out.write_text("\n".join(lines) + "\n")
    cli_utils.echo_success(f"Saved predictions: {out}")
    return PredictArtifacts(output_csv=out)
