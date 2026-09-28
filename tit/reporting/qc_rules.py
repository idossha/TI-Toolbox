"""Every QC rule a TI-Toolbox report applies, in one dict, each with its role, citation and plain text.

``RULES[section][key]`` holds:

* ``label`` — the check's name in a report;
* ``rule`` — ``>=``, ``<=``, ``==``, ``within`` or ``report`` (a value shown with a reference, no pass/fail);
* ``value`` and ``unit``;
* ``role`` — ``gate`` (blocks and is shown to the user), ``internal`` (a software consistency check:
  blocks too, shown only under Technical details), ``advisory`` (warns, never blocks) or ``report``;
* ``cite`` — DOIs, each also a reference in ``tit.reporting.reportlets.references``;
* ``note`` — where a value is TI-Toolbox's own rule rather than a published one;
* ``plain`` — one sentence a user can read, rendered next to the rule.

The pipelines (``tit.pre.qsi.dti_extractor``'s gate, ``tit.pre.qsi.dti_advisories``) and the reports
read values from here, so a value changes in one place. Rules and citations are from the literature
review of 2026-09-28 (the only published cut-offs for DTI are the b-table flip test; the rest are
internal invariants or values shown against a cited reference). Other report types add their own
section to ``RULES``.
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
}


def value(section: str, key: str):
    return RULES[section][key]["value"]
