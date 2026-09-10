"""The wall-clock model behind ``PlanCost.eta_minutes`` (:mod:`tit.jobs.eta`).

The properties tested are the ones the UI's promise rests on: an estimate grows with the thing
that actually drives the run (electrodes, pairs, combinations), an emulated machine is slower by
exactly the documented factor, running subjects in parallel divides, and a kind or an input the
model cannot read yields ``None`` rather than an invented number.

One calibration test pins the constants against the real ernie runs they were derived from (see
the module docstring's table), so a future edit to a constant fails here instead of silently
moving every number the UI shows.
"""

from __future__ import annotations

import os

import pytest

from tit.jobs import eta as eta_model
from tit.jobs.eta import SystemProfile, eta_minutes

NATIVE = SystemProfile(cpus=12, emulated=False, factor=1.0)
EMULATED = SystemProfile(cpus=12, emulated=True, factor=3.0)


@pytest.fixture()
def caps(tmp_path):
    """A project whose subject ``ernie`` has three caps of different sizes and ernie's mesh."""
    m2m = tmp_path / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie"
    positions = m2m / "eeg_positions"
    positions.mkdir(parents=True)
    for name, n in (("small", 19), ("medium", 75), ("big", 256)):
        rows = "\n".join(f"Electrode,0,0,0,E{i}" for i in range(n))
        (positions / f"{name}.csv").write_text(rows + "\n")
    with open(m2m / "ernie.msh", "wb") as fh:  # sparse: only the size is read
        fh.truncate(eta_model.REFERENCE_MESH_BYTES)

    from tit.paths import get_path_manager

    get_path_manager(str(tmp_path))
    eta_model.detect_system.cache_clear()
    return tmp_path


def _leadfield(net: str, **kw) -> float | None:
    return eta_minutes(
        "leadfield", {"subject_id": "ernie", "eeg_net": net}, system=EMULATED, **kw
    )


# --------------------------------------------------------------------------- system profile


def test_rosetta_vendor_string_is_detected_as_emulation() -> None:
    assert eta_model._is_emulated("x86_64", "vendor_id\t: VirtualApple\nflags\t: fpu sse2\n")


def test_x86_without_avx_is_detected_as_emulation() -> None:
    assert eta_model._is_emulated("x86_64", "vendor_id\t: GenuineIntel\nflags : fpu sse2 sse4_2\n")


def test_a_real_x86_host_is_not_emulated() -> None:
    assert not eta_model._is_emulated("x86_64", "vendor_id : GenuineIntel\nflags : fpu avx avx2\n")


def test_arm_is_never_emulation() -> None:
    assert not eta_model._is_emulated("arm64", "")


def test_more_cores_is_never_slower_and_the_factor_is_clamped() -> None:
    assert eta_model._cpu_factor(4) > eta_model._cpu_factor(12) >= eta_model._cpu_factor(64)
    assert 0.7 <= eta_model._cpu_factor(1024) <= 2.0
    assert eta_model._cpu_factor(1) == 2.0


# --------------------------------------------------------------------------- monotonicity


def test_leadfield_grows_with_the_number_of_electrodes(caps) -> None:
    small, medium, big = _leadfield("small"), _leadfield("medium"), _leadfield("big")
    assert small < medium < big
    # One FEM solve per electrode: 256 electrodes must cost far more than a 19-electrode cap,
    # which is the whole reason the button's hardcoded "40 min" was wrong.
    assert big > 5 * small


def test_leadfield_is_none_when_the_cap_cannot_be_read(caps) -> None:
    assert _leadfield("no-such-net") is None


def test_simulation_grows_with_the_number_of_pairs(caps) -> None:
    def sim(n_pairs: int, **cfg) -> float:
        montage = {"electrode_pairs": [["a", "b"]] * n_pairs}
        return eta_minutes(
            "sim", {"subject_id": "ernie", "montages": [montage], **cfg}, system=EMULATED
        )

    assert sim(2) < sim(4) < sim(8)
    # An anisotropic (DTI) conductivity model costs more than the isotropic default.
    assert sim(2, conductivity="vn") > sim(2, conductivity="scalar")


def test_a_batch_of_montages_costs_more_than_one(caps) -> None:
    one = {"subject_id": "ernie", "montages": [{"electrode_pairs": [["a", "b"], ["c", "d"]]}]}
    two = {"subject_id": "ernie", "montages": one["montages"] * 2}
    assert eta_minutes("sim", two, system=EMULATED) > eta_minutes("sim", one, system=EMULATED)


def test_ex_grows_with_the_combinations_the_buckets_imply(caps) -> None:
    def ex(n: int) -> float:
        return eta_minutes(
            "ex", {"subject_id": "ernie"}, resolved={"search_space": {"n_combinations": n}},
            system=EMULATED,
        )

    assert ex(7) < ex(2401) < ex(16807)


def test_ex_without_a_resolved_search_space_has_no_estimate(caps) -> None:
    assert eta_minutes("ex", {"subject_id": "ernie"}, system=EMULATED) is None


def test_flex_grows_with_multistart_and_with_the_de_budget(caps) -> None:
    base = {"subject_id": "ernie", "n_multistart": 1}
    assert eta_minutes("flex", base, system=EMULATED) < eta_minutes(
        "flex", {**base, "n_multistart": 4}, system=EMULATED
    )
    assert eta_minutes("flex", base, system=EMULATED) < eta_minutes(
        "flex", {**base, "max_iterations": 2000}, system=EMULATED
    )


def test_pre_sums_the_stages_the_planner_resolved(caps) -> None:
    resolved = {"stages": [{"tags": ["G2a"]}, {"tags": ["G2b"]}, {"tags": ["report"]}]}
    both = eta_minutes("pre", {}, resolved=resolved, system=EMULATED)
    charm_only = eta_minutes(
        "pre", {}, resolved={"stages": [{"tags": ["G2a"]}]}, system=EMULATED
    )
    assert both > charm_only


def test_an_unmodelled_kind_has_no_estimate(caps) -> None:
    assert eta_minutes("blender", {"subject_id": "ernie"}, system=EMULATED) is None


# --------------------------------------------------------------------------- machine / batching


def test_emulation_multiplies_by_exactly_the_documented_factor(caps) -> None:
    native = eta_minutes(
        "leadfield", {"subject_id": "ernie", "eeg_net": "medium"}, system=NATIVE
    )
    assert _leadfield("medium") == pytest.approx(native * eta_model.EMULATION_FACTOR, rel=0.01)


def test_a_bigger_mesh_costs_more(caps) -> None:
    one_subject = _leadfield("medium")
    mesh = caps / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie" / "ernie.msh"
    with open(mesh, "wb") as fh:
        fh.truncate(2 * eta_model.REFERENCE_MESH_BYTES)
    assert _leadfield("medium") > one_subject


def test_a_missing_mesh_falls_back_to_the_reference_scale(caps) -> None:
    assert eta_model.mesh_scale("nobody") == 1.0


def test_running_subjects_in_parallel_divides_the_wall_clock(caps) -> None:
    serial = _leadfield("medium", n_jobs=4, parallel=1)
    parallel = _leadfield("medium", n_jobs=4, parallel=4)
    assert serial == pytest.approx(4 * parallel, rel=0.01)


def test_parallel_lanes_beyond_the_job_count_do_not_help(caps) -> None:
    assert _leadfield("medium", n_jobs=2, parallel=8) == _leadfield(
        "medium", n_jobs=2, parallel=2
    )


# --------------------------------------------------------------------------- calibration


@pytest.mark.parametrize(
    "kind, config, resolved, measured",
    [
        # 76-electrode EEG10-10_UI_Jurak_2007 leadfield on ernie: 16:27:26 -> 16:50:27.
        ("leadfield", {"subject_id": "ernie", "eeg_net": "medium"}, None, 23.0),
        # one TI montage (2 pairs): 00:50:33 -> 00:56:10.
        (
            "sim",
            {"subject_id": "ernie", "montages": [{"electrode_pairs": [["a", "b"], ["c", "d"]]}]},
            None,
            5.6,
        ),
        # ex-search `docs_ex_large`, 16 807 combinations: ~14 min.
        ("ex", {"subject_id": "ernie"}, {"search_space": {"n_combinations": 16807}}, 14.0),
    ],
)
def test_the_model_reproduces_the_runs_it_was_calibrated_on(
    caps, kind, config, resolved, measured
) -> None:
    """Emulated, 12 cores, ernie's mesh -- the machine every constant was measured on."""
    got = eta_minutes(kind, config, resolved=resolved, system=EMULATED)
    assert got == pytest.approx(measured, rel=0.10)


def test_electrode_count_reads_the_cap_with_or_without_the_csv_suffix(caps) -> None:
    assert eta_model.electrode_count("ernie", "big") == 256
    assert eta_model.electrode_count("ernie", "big.csv") == 256
    assert eta_model.electrode_count("ernie", None) is None


def test_detect_system_reports_this_machine(caps) -> None:
    profile = eta_model.detect_system()
    assert profile.cpus == (os.cpu_count() or 1)
    assert profile.factor > 0
    assert set(profile.to_dict()) == {"cpus", "emulated", "factor"}
