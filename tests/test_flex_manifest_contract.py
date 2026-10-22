"""The flex_meta.json fixtures every reader is tested against are the writer's own output.

Pins (2026-10-22, package p12; precedent: ``tests/fixtures/flex_currents.json``):
* ``tests/fixtures/flex_meta_contract/*.json``, ``desktop/tests/fixtures/preview/flex_meta.json``
  and the ernie manifest in ``desktop/tests/fixtures/flex_runs.json`` are byte-for-byte what
  ``dev/regen_flex_manifest_fixtures.py`` produces with the real ``write_manifest``; a writer
  change fails here until the fixtures are regenerated (and the desktop readers' tests, which read
  the same files, run against the new shape);
* the writer keeps ROI fields in the shape the desktop sends them (lists, also for one region),
  states ``n_pairs`` (always 2: one electrode pair per TI channel) and the mapped ``eeg_net``
  (null without mapping), and writes a failed restart's ``inf`` as ``null`` (strict JSON).

Expected values come from the generator's inputs (its ``CASES`` table) and the docs
(docs/wiki/flex-search.md: "Flex-search optimizes exactly two electrode pairs"), never from a
previous manifest. Regenerate: ``python3 dev/regen_flex_manifest_fixtures.py``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _generator():
    spec = importlib.util.spec_from_file_location(
        "regen_flex_manifest_fixtures", ROOT / "dev" / "regen_flex_manifest_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _generator()
BUILT = GEN.build()


def _strict(raw: bytes) -> dict:
    def refuse(token):
        raise ValueError(f"non-strict JSON token {token}")

    return json.loads(raw, parse_constant=refuse)


def test_the_generator_has_cases_and_writes_every_fixture():
    assert len(GEN.CASES) >= 5
    assert {p.name for p in BUILT if p.parent == GEN.CONTRACT_DIR} == {
        f"{case}.json" for case in GEN.CASES
    }
    assert GEN.PREVIEW in BUILT and GEN.FLEX_RUNS in BUILT


@pytest.mark.parametrize("path", sorted(BUILT, key=str), ids=lambda p: p.name)
def test_committed_fixture_is_what_the_writer_produces(path):
    assert (
        path.is_file()
    ), f"{path} missing: run python3 dev/regen_flex_manifest_fixtures.py"
    assert path.read_bytes() == BUILT[path], (
        f"{path.relative_to(ROOT)} differs from write_manifest's output: "
        "run python3 dev/regen_flex_manifest_fixtures.py and update the readers"
    )


def test_the_package_writer_is_the_one_the_generator_ran(tmp_path, monkeypatch):
    """The generator loads manifest.py by path; the package import must write the same bytes."""
    import tit.opt.flex.manifest as manifest
    from tit.opt.config import FlexConfig

    class _Pinned(manifest.datetime):
        @classmethod
        def now(cls, tz=None):
            return GEN.CREATED

    monkeypatch.setattr(manifest, "datetime", _Pinned)
    kw, result, split = GEN.CASES["atlas_chn"]
    config = FlexConfig(
        subject_id="ernie",
        postproc="max_TI",
        current_mA=1.0,
        electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
        **kw,
    )
    path = manifest.write_manifest(
        str(tmp_path), config, result, "label-atlas_chn", current_split=split
    )
    assert Path(path).read_bytes() == BUILT[GEN.CONTRACT_DIR / "atlas_chn.json"]


@pytest.mark.parametrize("case", sorted(GEN.CASES))
def test_roi_fields_keep_the_shape_they_were_given(case):
    kw, _, _ = GEN.CASES[case]
    meta = _strict(BUILT[GEN.CONTRACT_DIR / f"{case}.json"])
    for key in ("roi", "non_roi"):
        given = kw.get(key)
        if given is None:
            assert meta[key] is None
            continue
        for field in ("x", "y", "z", "radius", "atlas_path", "label", "hemisphere"):
            if hasattr(given, field):
                assert meta[key][field] == getattr(given, field), (key, field)
                assert isinstance(meta[key][field], list)  # as the desktop sends them


@pytest.mark.parametrize("case", sorted(GEN.CASES))
def test_two_pairs_and_the_mapped_net(case):
    kw, result, _ = GEN.CASES[case]
    meta = _strict(BUILT[GEN.CONTRACT_DIR / f"{case}.json"])
    assert meta["n_pairs"] == 2
    assert meta["eeg_net"] == (kw["eeg_net"] if kw.get("enable_mapping") else None)
    assert meta["n_multistart"] == kw.get("n_multistart", 1)
    assert len(meta["result"]["all_values"]) == len(result.function_values)


def test_a_failed_restart_is_null_in_strict_json():
    meta = _strict(BUILT[GEN.CONTRACT_DIR / "focality_tf_specific_nonroi.json"])
    assert meta["result"]["all_values"] == [-1.59, None]
    assert meta["current_split"] == [0.9, 1.1]


def test_the_mock_catalog_run_carries_the_generated_manifest_and_agrees_with_its_mapping():
    runs = json.loads(BUILT[GEN.FLEX_RUNS])
    (run,) = runs["ernie"]
    meta = _strict(BUILT[GEN.CONTRACT_DIR / "subcortical_union_mapped.json"])
    assert run["manifest"] == meta
    assert run["roi"] == meta["roi"] and run["goal"] == meta["goal"]
    assert run["created"] == meta["created"]
    # tit.catalog.flex_runs derives these three from the manifest the same way.
    assert [m["eeg_net"] for m in run["mappings"]] == [meta["eeg_net"]]
