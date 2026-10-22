#!/usr/bin/env python3
"""Write the flex_meta.json fixtures every reader of a flex run is tested against.

``tit/opt/flex/manifest.py::write_manifest`` is the only writer of ``flex_meta.json``; the Results
preview (``desktop/src/renderer/pages/results/preview/flex.ts``), the mock server's catalog
(``desktop/tests/fixtures/flex_runs.json``) and ``tit.catalog.flex_runs`` read it. Hand-written
fixtures drifted from it (scalar ``atlas_path``/``label`` where the writer stores the lists the
desktop sends), so these are written by the real writer from the synthetic ``FlexConfig``s below:

* ``tests/fixtures/flex_meta_contract/<case>.json``, one per case in :data:`CASES`;
* ``desktop/tests/fixtures/preview/flex_meta.json``, a copy of ``subcortical_focality``;
* the ``manifest`` (and the ``goal``/``roi``/``created`` the catalog derives from it) of the mock
  catalog's one ernie run in ``desktop/tests/fixtures/flex_runs.json``, from
  ``subcortical_union_mapped``.

``created`` is pinned to :data:`CREATED`; everything else is what the writer emits.
``tests/test_flex_manifest_contract.py`` fails when a committed file differs from this output,
so a writer change lands together with its regenerated fixtures and the readers' tests.

Regenerate: ``python3 dev/regen_flex_manifest_fixtures.py`` (host Python with the repo on the
path; no SimNIBS). Deterministic: ``git diff`` after a run is empty unless the writer changed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tit.opt.config import FlexConfig, FlexResult  # noqa: E402

CONTRACT_DIR = ROOT / "tests" / "fixtures" / "flex_meta_contract"
PREVIEW = ROOT / "desktop" / "tests" / "fixtures" / "preview" / "flex_meta.json"
FLEX_RUNS = ROOT / "desktop" / "tests" / "fixtures" / "flex_runs.json"
CREATED = datetime(2026, 8, 10, 10, 15, 0)

_EX = "/mnt/example/derivatives"
MASSP = "/ti-toolbox/resources/atlas/massp2021-parcellation_decade-18to40.nii.gz"
E = FlexConfig.ElectrodeConfig


def _result(values: list[float], best: int) -> FlexResult:
    finite = [v for v in values if v == v and abs(v) != float("inf")]
    return FlexResult(
        success=bool(finite),
        output_folder="",
        function_values=values,
        best_value=values[best] if finite else float("inf"),
        best_run_index=best if finite else -1,
    )


#: case -> (FlexConfig kwargs, result, current_split). Shapes are the ones the desktop sends
#: (tests/fixtures/desktop_configs/optimizer-flex/: list x/y/z/radius, list atlas fields).
CASES: dict[str, tuple[dict, FlexResult, tuple[float, float] | None]] = {
    "sphere_desktop": (
        dict(
            goal="mean",
            roi=FlexConfig.SphericalROI(x=[-30.0], y=[10.0], z=[5.0], radius=[10.0]),
        ),
        _result([-0.21], 0),
        None,
    ),
    "sphere_union": (
        dict(
            goal="max",
            roi=FlexConfig.SphericalROI(
                x=[-30.0, 30.0],
                y=[10.0, 12.0],
                z=[5.0, 6.0],
                radius=[10.0, 8.0],
                volumetric=True,
                tissues="GM",
            ),
            n_multistart=2,
        ),
        _result([-0.42, -0.4], 0),
        None,
    ),
    "atlas_chn": (
        dict(
            goal="mean",
            roi=FlexConfig.AtlasROI(
                atlas_path=[
                    f"{_EX}/SimNIBS/sub-CHN/m2m_CHN/segmentation/lh.CHN_DK40.annot"
                ],
                label=[35],
                hemisphere=["lh"],
            ),
        ),
        _result([-0.3646788191392692], 0),
        None,
    ),
    "subcortical_union_mapped": (
        dict(
            goal="focality_tf",
            current_mA=2.0,
            roi=FlexConfig.SubcorticalROI(
                atlas_path=[MASSP, MASSP],
                label=[13, 14],
                atlas_space="mni",
                tissues="GM",
            ),
            non_roi_method="everything_else",
            n_multistart=2,
            enable_mapping=True,
            eeg_net="GSN-HydroCel-185.csv",
        ),
        _result([-91.5566569075475, -84.39278350962034], 0),
        None,
    ),
    "subcortical_focality": (
        dict(
            goal="focality",
            current_mA=2.0,
            thresholds="0.1,0.2",
            roi=FlexConfig.SubcorticalROI(
                atlas_path=[
                    f"{_EX}/SimNIBS/sub-ernie/m2m_ernie/segmentation/labeling.nii.gz"
                ],
                label=[17],
                atlas_space="subject",
                tissues="GM",
            ),
            non_roi_method="everything_else",
            n_multistart=2,
        ),
        _result([-91.5566569075475, -84.39278350962034], 0),
        None,
    ),
    "focality_tf_specific_nonroi": (
        dict(
            goal="focality_tf",
            intensity_weight=0.5,
            roi=FlexConfig.SphericalROI(x=[-30.0], y=[10.0], z=[5.0], radius=[10.0]),
            non_roi_method="specific",
            non_roi=FlexConfig.SphericalROI(
                x=[30.0], y=[-20.0], z=[40.0], radius=[15.0]
            ),
            optimize_current_ratio=True,
            n_multistart=2,
        ),
        # Restart 2 accepted no candidate: inf, which strict JSON writes as null.
        _result([-1.59, float("inf")], 0),
        (0.9, 1.1),
    ),
}


def _writer():
    """``tit/opt/flex/manifest.py`` loaded by path: importing ``tit.opt.flex`` pulls in the
    optimiser and its plotting stack, which the writer itself does not use."""
    path = ROOT / "tit" / "opt" / "flex" / "manifest.py"
    spec = importlib.util.spec_from_file_location("_flex_manifest_writer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build() -> dict[Path, bytes]:
    """Every fixture this script owns, ``{path: bytes}``, without writing anything."""
    manifest = _writer()

    class _Pinned(datetime):
        @classmethod
        def now(cls, tz=None):
            return CREATED

    manifest.datetime = _Pinned
    out: dict[Path, bytes] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for case, (kw, result, split) in CASES.items():
            config = FlexConfig(
                **{
                    "subject_id": "ernie",
                    "postproc": "max_TI",
                    "current_mA": 1.0,
                    "electrode": E(shape="ellipse", dimensions=[8.0, 8.0]),
                    **kw,
                }
            )
            folder = Path(tmp, case)
            folder.mkdir()
            path = manifest.write_manifest(
                str(folder), config, result, f"label-{case}", current_split=split
            )
            out[CONTRACT_DIR / f"{case}.json"] = Path(path).read_bytes()

    out[PREVIEW] = out[CONTRACT_DIR / "subcortical_focality.json"]
    runs = json.loads(FLEX_RUNS.read_text())
    meta = json.loads(out[CONTRACT_DIR / "subcortical_union_mapped.json"])
    runs["ernie"][0].update(
        goal=meta["goal"], roi=meta["roi"], created=meta["created"], manifest=meta
    )
    out[FLEX_RUNS] = (json.dumps(runs, indent=2) + "\n").encode()
    return out


def main() -> int:
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    for path, data in build().items():
        path.write_bytes(data)
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
