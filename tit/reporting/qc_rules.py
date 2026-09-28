"""Every QC rule a TI-Toolbox report applies, in one dict, each with its role, citation and plain text.

``RULES[section][key]`` holds:

* ``label`` — the check's name in a report;
* ``rule`` — ``>=``, ``<=``, ``<``, ``==``, ``within`` or ``report`` (a value shown with a reference, no pass/fail);
* ``value`` and ``unit``;
* ``role`` — ``gate`` (blocks and is shown to the user), ``internal`` (a software consistency check:
  blocks too, shown only under Technical details), ``advisory`` (warns, never blocks) or ``report``;
* ``cite`` — DOIs, each also a reference in ``tit.reporting.references``;
* ``note`` — where a value is TI-Toolbox's own rule rather than a published one;
* ``plain`` — one sentence a user can read, rendered next to the rule.

The pipelines (``tit.pre.qsi.dti_extractor``'s gate, ``tit.pre.qsi.dti_advisories``) and the reports
read values from here, so a value changes in one place. Rules and citations are from the literature
review of 2026-09-28 (the only published cut-offs for DTI are the b-table flip test; the rest are
internal invariants or values shown against a cited reference). ``sim`` and ``opt`` hold the
simulator and optimiser rules (the same review); the simulator's ``electrode_peak_current`` is per
electrode, which carries its channel's current. The optimiser reports have no checks: ``opt`` holds
only the goal definition and dose record they cite as prose.
"""

from __future__ import annotations

RULES: dict[str, dict[str, dict]] = {
    "dti": {
        "ncc_chain": {
            "label": "Registration to the head model",
            "rule": ">=",
            "value": 0.90,
            "unit": "",
            "role": "internal",
            "cite": [],
            "note": "",
            "plain": "The T1 carried through our transform matches the head-model T1 (same image, so close to 1 is expected).",
        },
        "chain_vs_ncc_mm": {
            "label": "Transform agreement",
            "rule": "<=",
            "value": 1.0,
            "unit": "mm",
            "role": "internal",
            "cite": ["10.1038/s41592-018-0235-4"],
            "note": "15 mm catastrophe heuristic (fMRIPrep); 1 mm = one head-model voxel (ours)",
            "plain": "Two independent registrations agree to within one voxel.",
        },
        "pct_pd": {
            "label": "Positive-definite tensors",
            "rule": ">=",
            "value": 99.0,
            "unit": "%",
            "role": "internal",
            "cite": [],
            "note": "",
            "plain": "Nearly all fitted tensors are physically valid.",
        },
        "pct_wmgm_zero": {
            "label": "WM and GM without a tensor",
            "rule": "<=",
            "value": 5.0,
            "unit": "%",
            "role": "internal",
            "cite": [],
            "note": "",
            "plain": "Almost all white and grey matter received a tensor.",
        },
        "n_out_of_brain": {
            "label": "Tensors outside the brain",
            "rule": "==",
            "value": 0,
            "unit": "voxels",
            "role": "internal",
            "cite": [],
            "note": "",
            "plain": "No tensors were written outside the brain.",
        },
        "wm_md_median": {
            "label": "White-matter diffusivity",
            "rule": "within",
            "value": [0.5e-3, 1.1e-3],
            "unit": "mm²/s",
            "role": "gate",
            "cite": ["10.1148/radiology.201.3.8939209", "10.1038/ncomms13629"],
            "note": "",
            "plain": "White-matter diffusivity is near the healthy-adult value (~0.7e-3 mm²/s); far outside it usually means a b-value or unit error.",
        },
        "flip_identity_best": {
            "label": "Gradient-table flip test",
            "rule": "==",
            "value": True,
            "unit": "",
            "role": "advisory",
            "cite": ["10.1016/j.media.2014.05.012", "10.1016/j.mri.2019.01.018"],
            "note": "no published margin",
            "plain": "The gradient directions as given fit the anatomy better than any flipped or swapped version.",
        },
        "tract_frac_expected": {
            "label": "Tract orientation",
            "rule": ">=",
            "value": 0.5,
            "unit": "fraction",
            "role": "advisory",
            "cite": [],
            "note": "majority rule (ours); no published threshold",
            "plain": "Most corpus callosum, corticospinal and cingulum voxels point the way these tracts run.",
        },
        "sdc_applied": {
            "label": "Distortion correction",
            "rule": "==",
            "value": True,
            "unit": "",
            "role": "advisory",
            "cite": ["10.1002/mrm.1910340111", "10.1038/s41592-021-01185-5"],
            "note": "",
            "plain": "EPI distortion was corrected; without it, frontal and temporal tensors can be shifted by a few mm.",
        },
        "residual_shift_mm": {
            "label": "Residual distortion",
            "rule": "<=",
            "value": "1 DWI voxel",
            "unit": "mm",
            "role": "advisory",
            "cite": [],
            "note": "unit-based (ours); no published threshold",
            "plain": "FA lines up with the head-model white matter to within one diffusion voxel.",
        },
        "mean_fd_mm": {
            "label": "Head motion",
            "rule": "report",
            "value": None,
            "unit": "mm",
            "role": "report",
            "cite": [
                "10.1016/j.neuroimage.2015.10.068",
                "10.1016/j.neuroimage.2013.11.027",
            ],
            "note": "Roalf 2016 rated > 0.82 mm poor, with a different motion measure on a single protocol",
            "plain": "Average head movement between diffusion volumes; lower is better.",
        },
        "wm_fa_median": {
            "label": "White-matter FA",
            "rule": "report",
            "value": None,
            "unit": "",
            "role": "report",
            "cite": ["10.1093/cercor/bhp280", "10.1016/j.neuroimage.2011.11.094"],
            "note": "",
            "plain": "White-matter anisotropy, shown next to the reference subject; it varies with age and scanner.",
        },
        "qsiprep_iqms": {
            "label": "QSIPrep image quality",
            "rule": "report",
            "value": None,
            "unit": "",
            "role": "report",
            "cite": [
                "10.1016/j.neuroimage.2019.116131",
                "10.1038/s41592-021-01185-5",
                "10.1016/j.neuroimage.2016.06.058",
            ],
            "note": "",
            "plain": "QSIPrep image-quality numbers; there are no accepted cut-offs, so compare within a study.",
        },
    },
    # Simulation and optimisation rules (literature review 2026-09-28). The only published
    # cut-offs are the tES current evidence (< 4 mA), the brain-injury current density
    # (6.3 A/m²) and Cassarà 2025's frequency-dependent TI limits; the rest are TI-Toolbox's own
    # consistency checks or values shown against a cited range. Current checks are advisories.
    "sim": {
        "solver_rtol": {
            "label": "Solver precision",
            "rule": "<=",
            "value": 1e-10,
            "unit": "",
            "role": "internal",
            "cite": [],
            "note": "SimNIBS fem.py default",
            "plain": "The field solver converged to SimNIBS's default precision.",
        },
        "channel_current_sum": {
            "label": "Current conservation",
            "rule": "==",
            "value": 0.0,
            "unit": "mA",
            "role": "internal",
            "cite": [],
            "note": "current conservation",
            "plain": "Each channel's current in equals current out.",
        },
        "mesh_quality": {
            "label": "Head model",
            "rule": "report",
            "value": None,
            "unit": "",
            "role": "report",
            "cite": ["10.1016/j.neuroimage.2020.117044"],
            "note": "",
            "plain": "Head model tissue outlines, to check by eye; no numeric standard exists.",
        },
        "roi_envelope_V_per_m": {
            "label": "Target field",
            "rule": "report",
            "value": "0.24–0.57 V/m at 2 mA total (optimised)",
            # The same band as numbers, for drawing it; the text above is the cited value.
            "range": [0.24, 0.57],
            "at_mA_total": 2.0,
            "unit": "V/m",
            "role": "report",
            "cite": ["10.1016/j.neuroimage.2019.116124", "10.7554/eLife.18834"],
            "note": "",
            "plain": "Target field strength compared with published TI and tES values.",
        },
        "peak_field_order_check": {
            "label": "Field order of magnitude",
            "rule": "within",
            "value": [0.01, 5.0],
            "unit": "V/m per mA total",
            "role": "internal",
            "cite": ["10.7554/eLife.18834"],
            "note": "order-of-magnitude band (ours), anchored on Huang 2017",
            "plain": "Catches unit or scaling errors (e.g. A vs mA).",
        },
        "brain_peak_J": {
            "label": "Brain current density",
            "rule": "<",
            "value": 6.3,
            "unit": "A/m²",
            "role": "advisory",
            "cite": ["10.1016/j.brs.2016.06.004"],
            "note": "",
            "plain": "Peak brain current density versus the lowest injury level seen in animals.",
        },
        "electrode_peak_current": {
            "label": "Electrode current",
            "rule": "<",
            "value": 4.0,
            "unit": "mA",
            "role": "advisory",
            "cite": [
                "10.1016/j.clinph.2017.06.001",
                "10.1016/j.brs.2016.06.004",
                "10.1002/bem.22536",
            ],
            "note": "TI kHz limits: Cassarà 2025",
            "plain": "Within the current range with established tES safety evidence; TI at kHz has higher, frequency-dependent limits.",
        },
    },
    "opt": {
        "goal_definition": {
            "label": "Goal definition",
            "rule": "report",
            "value": None,
            "unit": "",
            "role": "report",
            "cite": [
                "10.1016/j.neuroimage.2019.116183",
                "10.1016/j.compbiomed.2025.110648",
            ],
            "note": "",
            "plain": "Exactly how 'intensity' and 'focality' were measured.",
        },
        "dose_record": {
            "label": "Dose record",
            "rule": "report",
            "value": None,
            "unit": "",
            "role": "report",
            "cite": ["10.1016/j.brs.2011.10.001"],
            "note": "",
            "plain": "Montage, electrode size, currents and frequencies: everything needed to reproduce the dose.",
        },
    },
}


def value(section: str, key: str):
    return RULES[section][key]["value"]
