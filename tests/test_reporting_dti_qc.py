"""DTI QC report, the shared report layer and the QC rules: structure, not pixels.

Pins (2026-09-28, ARCHITECTURE.md §14):
* the page has its six sections, every contents link lands on an element, every image has alt
  text, every figure a caption, and nothing is fetched from the network (doi.org links only);
* blocking rows take their status from the record's ``failures``, so a table cannot disagree with
  the verdict; a failing record renders a "Failed" verdict and the report is still written;
* the default view shows only the user-facing gate; software checks sit under Technical details;
  advisories show a callout only when they need attention;
* every rule in ``tit.reporting.qc_rules`` has a known role and plain text, and every DOI it cites
  is in the reference registry; every row shows its role and status as icon + word;
* every colour token is redefined in both dark scopes; the gate rail clamps to its track;
* ``extract_dti_tensor`` writes the QC record and the report before it raises on a failed gate.

The numbers are inputs, not expectations: gate values are CHN's recorded QC (as in
tests/test_pre_qsi_dti.py), metrics are synthetic. Images are stand-in bytes; the real renderer,
the advisories and the size budget run in tests/numerical/test_dti_advisories.py, and on CHN via
``python -m tit.reporting.generators.dti_qc``. No pixel goldens.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit.pre.qsi import dti_advisories as adv
from tit.pre.qsi.dti_extractor import DtiQc
from tit.reporting.generators import dti_qc as gen
from tit.reporting.html import components as c
from tit.reporting.qc_rules import RULES
from tit.reporting.reportlets.references import get_reference_by_doi

SECTIONS = ("verdict", "preprocessing", "registration", "orientation", "diffusivity", "technical")
FAKE = b"RIFF\x00\x00\x00\x00WEBPVP8 "


def _images() -> dict:
    plane = {"t1": FAKE, "fa": FAKE, "labels": [f"z = {i:+d}" for i in range(6)], "cols": 3, "tile": (100, 80), "shape": (204, 248)}
    return {"is_mni": True, "registration": {"axial": plane, "coronal": plane, "sagittal": plane},
            "dec": {"z": [16, 20, 24], "frames": [FAKE] * 3}, "sphere": b"\x89PNG",
            "sphere_axes": {"R": [0.5, -0.2], "A": [0.4, -0.3], "S": [0.0, 0.8]}}


def _record(overrides: dict | None = None, sdc_applied: bool = False) -> dict:
    values = dict(ncc_chain=0.984, chain_vs_ncc_mm=0.038, pct_pd=100.0, pct_wm_covered=98.9, pct_gm_covered=99.5,
                  pct_wmgm_zero=0.81, wm_md_median=0.677e-3, wm_fa_median=0.323, n_out_of_brain=0)
    values.update(overrides or {})
    qc = DtiQc(**values)
    qc.gate()
    record = asdict(qc)
    rng = np.random.default_rng(0)
    labv = rng.integers(1, 4, 3000)
    w = np.sort(rng.uniform(0.2e-3, 1.8e-3, (3000, 3)), axis=1)[:, ::-1]
    tracts = {k: {"name": n, "expected": "L–R", "n": 500, "fa_mean": 0.6, "frac_expected": 0.9, "mean_abs_v1": [0.8, 0.3, 0.2]}
              for k, (n, _, _) in adv.TRACTS.items()}
    shift = {name: {"n": 1000, "corr0": 0.6, "best_ap_mm": 1.0, "best_si_mm": 3.0 if "Front" in name else 0.0, "gain": 0.1}
             for name in ("Frontal (y > 30)", "Posterior (y < −40)")}
    scores = {f"{p} {f}": 0.99 - 0.001 * i for i, (p, f) in enumerate((p, f) for p in ("xyz", "yxz") for f in ("none", "flip x"))}
    metrics = {"grid": {"shape": [176, 256, 256], "zooms": [1.0, 1.0, 1.0]},
               "fa_bins": adv.FA_BINS.tolist(), "md_bins": adv.MD_BINS.tolist(),
               "tissue": adv.tissue_stats(rng.uniform(0, 1, 3000), w.mean(1), labv),
               "conductivity": adv.conductivity_preview(w, labv),
               "flip_test": {"scores": scores, "n_seeds": 60000, "best": "xyz none", "runner_up": "xyz flip x"},
               "tracts": tracts, "residual_shift": shift}
    sdc = {"reported": "TOPUP" if sdc_applied else "None", "applied": sdc_applied, "pe_direction": "Anterior-Posterior",
           "pepolar_method": "TOPUP", "use_syn_sdc": False,
           "dwi_fmaps": [{"file": "sub-X_acq-dwi_dir-PA_epi.nii.gz", "has_json": False, "pe": None, "intended_for": []}]}
    mot = {"fd": [0.0, 0.5, 0.9, 0.4], "mean_fd": 0.6, "max_fd": 0.9, "max_rotation": 0.01, "max_translation": 1.3,
           "num_bad_slices": 0.0, "neighbor_corr": 0.94, "t1_dice_distance": 0.036}
    acq = {"scanner": {"Manufacturer": "Siemens", "ManufacturersModelName": "Prisma_fit", "MagneticFieldStrength": 3, "EchoTime": 0.082,
                       "RepetitionTime": 5.0, "PhaseEncodingDirection": "j-"},
           "raw_dims": [116.0, 116.0, 74.0], "raw_voxel_mm": [2.0, 2.0, 2.0], "bvals": [0.0, 1200.0, 3000.0, 1200.0],
           "shells": {"0": 1, "1200": 2, "3000": 1},
           "qsiprep": {"version": "26.0.0", "command": "qsiprep /data /out participant <script>", "date": "2026-09-27",
                       "denoise_method": "dwidenoise", "unringing_method": "mrdegibbs", "hmc_model": "eddy", "hmc_transform": "Affine",
                       "b0_to_t1w_transform": "Rigid", "output_resolution": 1.0}}
    record.update({"advisories": adv.advisories(metrics, sdc, mot, acq, reference_fa=0.36), "metrics": metrics, "acquisition": acq,
                   "motion": mot, "sdc": sdc, "reference": {"subject": "ernie", "wm_fa_median": 0.36},
                   "provenance": {"recorded_by": "test", "created": "2026-09-28 00:00:00", "versions": {"ti_toolbox": "3.0.1", "dipy": "1.12.0"},
                                  "config": {"DTI_BMAX": 1500}, "config_hash": "ab" * 32,
                                  "inputs": {"tensor": {"path": "<project>/t.nii.gz", "sha256": "cd" * 32, "bytes": 1000}}}})
    return record


class _Page(HTMLParser):
    """Collects what the structural checks need from one page."""

    def __init__(self) -> None:
        super().__init__()
        self.ids, self.imgs, self.urls, self.toc, self.statuses = set(), [], [], [], []
        self.figures = self.captions = 0
        self._toc = self._status = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.ids.add(a.get("id"))
        self.urls += [a[k] for k in ("src", "href") if a.get(k, "").startswith(("http:", "https:", "//"))]
        self.imgs += [a.get("alt", "")] if tag == "img" else []
        self.figures += tag == "figure"
        self.captions += tag == "figcaption"
        if tag == "ol" and a.get("class") == "toc":
            self._toc = True
        if tag == "a" and self._toc:
            self.toc.append(a["href"])
        if tag == "span" and "st" in (a.get("class") or "").split() and not self._toc:
            self.statuses.append([a["class"], False, ""])
            self._status = True
        if tag == "svg" and self._status:
            self.statuses[-1][1] = True

    def handle_endtag(self, tag):
        self._toc = self._toc and tag != "ol"
        self._status = self._status and tag != "span"

    def handle_data(self, data):
        if self._status:
            self.statuses[-1][2] += data.strip()


def _parse(html: str) -> _Page:
    page = _Page()
    page.feed(html)
    return page


def _row_statuses(table_html: str) -> list[str]:
    return re.findall(r'<tr><td class=""><span class="st (\w+)"', table_html)


def _tables(html: str) -> list[str]:
    return [t.split("</table>")[0] for t in html.split('<table class="tbl gate">')[1:]]


class TestPageStructure:
    def test_sections_links_images_captions_offline(self):
        html = gen.build_html(_record(), _images(), "X")
        page = _parse(html)
        assert all(s in page.ids for s in SECTIONS)
        assert page.toc and all(h.startswith("#") and h[1:] in page.ids for h in page.toc)
        assert page.imgs and all(alt.strip() for alt in page.imgs)
        assert page.figures >= 3 and page.figures == page.captions
        assert page.urls and all(u.startswith("https://doi.org/") for u in page.urls), page.urls
        assert "url(http" not in html and "@import" not in html
        assert "&lt;script&gt;" in html  # the recorded QSIPrep command is shown escaped

    def test_status_is_icon_and_word(self):
        statuses = _parse(gen.build_html(_record(), _images(), "X")).statuses
        assert statuses and all(has_icon and word for _, has_icon, word in statuses), statuses

    def test_every_row_shows_its_role(self):
        html = gen.build_html(_record(), _images(), "X")
        for table in _tables(html):
            assert table.count('<span class="role ') == len(_row_statuses(table))


class TestChecks:
    def test_default_view_shows_only_the_gate_and_details_hold_the_software_checks(self):
        gate_table, all_checks = _tables(gen.build_html(_record(), _images(), "X"))
        assert _row_statuses(gate_table) == ["pass"]
        assert "White-matter diffusivity" in gate_table and "Transform agreement" not in gate_table
        assert all_checks.count('class="role internal"') == 5

    def test_passing_record_verdict_callouts_and_tensor_date(self):
        html = gen.build_html(_record(), _images(), "X", tensor_written=datetime(2026, 9, 27, 14, 3))
        assert '<h2 id="verdict-h">Quality gate passed · 2 advisories need attention</h2>' in html
        assert "<dt>Tensor written</dt><dd>2026-09-27 14:03</dd>" in html
        verdict = html.split('id="verdict"')[1].split("</section>")[0]
        assert "No susceptibility distortion correction." in verdict and "sub-X_acq-dwi_dir-PA_epi.nii.gz" in verdict

    def test_no_callout_when_nothing_needs_attention(self):
        record = _record(sdc_applied=True)
        record["metrics"]["residual_shift"] = {"Frontal (y > 30)": {"n": 1, "corr0": 0.6, "best_ap_mm": 0.0, "best_si_mm": 1.0, "gain": 0.0}}
        record["advisories"] = adv.advisories(record["metrics"], record["sdc"], record["motion"], record["acquisition"], 0.36)
        html = gen.build_html(record, _images(), "X")
        assert '<h2 id="verdict-h">Quality gate passed</h2>' in html and "need attention" not in html
        assert 'class="callout' not in html.split('id="verdict"')[1].split("</section>")[0]

    def test_failing_record_names_the_failed_checks_and_opens_them(self):
        record = _record({"ncc_chain": 0.5, "n_out_of_brain": 3})
        assert record["failures"] == ["ncc_chain", "n_out_of_brain"]
        html = gen.build_html(record, _images(), "X")
        assert "Software checks failed: Registration to the head model, Tensors outside the brain — tensor not written" in html
        assert "<dt>Tensor</dt><dd><b>not written</b></dd>" in html
        assert '<details class="raw" open><summary>All checks' in html
        assert _row_statuses(_tables(html)[1])[:5] == ["fail", "pass", "pass", "pass", "fail"]

    def test_failed_gate_is_named_as_the_quality_gate(self):
        html = gen.build_html(_record({"wm_md_median": 2.0e-3}), _images(), "X")
        assert "Quality gate failed: White-matter diffusivity — tensor not written" in html

    def test_row_status_comes_from_failures_not_from_the_value(self):
        record = _record()
        record["failures"] = ["pct_pd"]
        rows = gen.gate_checks(record)
        assert [r.status for r in rows] == ["pass", "pass", "fail", "pass", "pass", "pass"]
        assert c.verdict(rows)[0] == "fail"

    def test_unknown_status_or_role_rejected(self):
        with pytest.raises(ValueError):
            c.Check("g", "G", "", "", "", "ok")
        with pytest.raises(ValueError):
            c.Check("g", "G", "", "", "", "pass", role="maybe")


class TestRules:
    def test_every_rule_has_role_plain_text_and_resolvable_citations(self):
        for section, rules in RULES.items():
            for key, r in rules.items():
                assert r["role"] in c.ROLE_WORD and r["plain"].strip(), (section, key)
                for doi in r["cite"]:
                    assert get_reference_by_doi(doi), (section, key, doi)

    def test_gate_and_records_agree_on_the_rules(self):
        record = _record()
        assert {row.id for row in gen.gate_checks(record)} == {k for k, r in RULES["dti"].items() if r["role"] in ("gate", "internal")}
        assert {a["id"] for a in record["advisories"]} <= set(RULES["dti"])

    def test_cited_references_are_listed(self):
        html = gen.build_html(_record(), _images(), "X")
        cited = set(re.findall(r'href="#ref-([\w]+)"', html))
        listed = set(re.findall(r'<li id="ref-([\w]+)"', html))
        assert cited and cited == listed


class TestSharedLayer:
    def test_every_colour_token_has_both_dark_definitions(self):
        css = (Path(c.__file__).parent / "report.css").read_text()
        root = css.split(":root{", 1)[1].split("}", 1)[0]
        media = css.split(':root:not([data-theme="light"]){', 1)[1].split("}", 1)[0]
        explicit = css.split(':root[data-theme="dark"]{', 1)[1].split("}", 1)[0]

        def tokens(block: str, colours_only: bool = False) -> set[str]:
            return {k for k, v in re.findall(r"(--[\w-]+):\s*([^;]+);", block) if not colours_only or v.strip().startswith(("#", "rgb"))}

        colours = tokens(root, colours_only=True) - {"--lightbox", "--on-lightbox", "--on-lightbox-2"}  # the imaging surround stays dark
        assert colours and colours <= tokens(media) and tokens(media) == tokens(explicit)

    def test_gate_scale_clamps_to_the_track(self):
        def cx(svg: str) -> float:
            return float(re.search(r'<circle cx="([\d.]+)"', svg).group(1))

        assert cx(c.gate_scale(-50, 0, 10, (0, 5))) == cx(c.gate_scale(0, 0, 10, (0, 5))) == 6.0
        assert cx(c.gate_scale(1e9, 0, 10, (0, 5))) == cx(c.gate_scale(10, 0, 10, (0, 5))) == 184.0

    def test_images_need_alt_text(self):
        with pytest.raises(ValueError):
            c.img(FAKE, "")

    def test_inline_escapes_and_marks_code(self):
        assert c.inline("a <b> `IntendedFor`") == "a &lt;b&gt; <code>IntendedFor</code>"

    def test_fonts_are_embedded_once(self):
        html = c.page(title="t", kind="k", subject="s", toc=[], body="")
        assert html.count("@font-face") == 4 and html.count("font/woff2") == 4


class TestReportFile:
    def test_failed_record_still_writes_a_report(self, tmp_path):
        with patch("tit.plotting.dti_qc.render_all", return_value=_images()):
            path = gen.create_dti_qc_report(tmp_path, "X", _record({"pct_pd": 50.0}), vols=None, out_dir=tmp_path / "out")
        assert path.parent == tmp_path / "out" and path.name.startswith("dti_qc_")
        assert "Software check failed: Positive-definite tensors" in path.read_text()


# ── extract_dti_tensor: QC record and report before the raise ────────────


def _project(tmp_path: Path) -> Path:
    m2m = tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001"
    m2m.mkdir(parents=True)
    for name in ("T1.nii.gz", "final_tissues.nii.gz"):
        (m2m / name).touch()
    (tmp_path / "sub-001" / "anat").mkdir(parents=True)
    (tmp_path / "sub-001" / "anat" / "sub-001_T1w.nii.gz").touch()
    sub = tmp_path / "derivatives" / "qsiprep" / "sub-001"
    for rel in ("dwi/sub-001_space-ACPC_desc-preproc_dwi.nii.gz", "dwi/sub-001_space-ACPC_desc-preproc_dwi.b",
                "dwi/sub-001_space-ACPC_desc-brain_mask.nii.gz", "anat/sub-001_from-ACPC_to-anat_mode-image_xfm.mat",
                "anat/sub-001_space-ACPC_desc-preproc_T1w.nii.gz", "anat/sub-001_space-ACPC_desc-brain_mask.nii.gz"):
        (sub / rel).parent.mkdir(parents=True, exist_ok=True)
        (sub / rel).touch()
    return m2m


@pytest.mark.parametrize("ncc,passes", [(0.5, False), (0.98, True)])
def test_extract_writes_record_and_report_then_raises(tmp_path, ncc, passes):
    from tit.paths import get_path_manager, reset_path_manager
    from tit.pre.qsi import dti_extractor as dx
    from tit.pre.utils import PreprocessError

    m2m = _project(tmp_path)
    shape = (6, 6, 6)
    labels = np.full(shape, 1, np.uint8)
    labels[0] = 0

    def fake_load(path):
        img = MagicMock()
        img.shape, img.affine = shape, np.eye(4)
        img.dataobj = labels if path.endswith("final_tissues.nii.gz") else np.ones(shape, np.float32)
        return img

    tensors = np.zeros(shape + (3, 3))
    tensors[...] = np.diag([1.4e-3, 0.4e-3, 0.4e-3])
    order: list = []
    reset_path_manager()
    get_path_manager(str(tmp_path))
    try:
        with (
            patch("nibabel.load", side_effect=fake_load),
            patch("scipy.ndimage.binary_dilation", side_effect=lambda a, iterations: a),
            patch.object(dx, "fit_tensor", return_value=(tensors, np.eye(4), np.ones(shape, bool))),
            patch.object(dx, "read_itk_transform", return_value=np.eye(4)),
            patch.object(dx.tm, "acpc_to_t1_world", return_value=np.eye(4)),
            patch.object(dx, "check_registration", return_value=(ncc, 0.04)),
            patch.object(dx, "resample_tensor", return_value=(tensors, np.ones(shape, bool))),
            patch.object(dx, "_save_nifti_gz", side_effect=lambda *a: order.append("tensor")),
            patch("tit.pre.qsi.dti_advisories.DtiVolumes.from_arrays", return_value="vols"),
            patch.object(dx, "record_advisories", side_effect=lambda rec, *a, **k: order.append("advisories")),
            patch.object(gen, "create_dti_qc_report", side_effect=lambda p, s, rec, vols: order.append(("report", tuple(rec["failures"])))),
        ):
            if passes:
                dx.extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())
            else:
                with pytest.raises(PreprocessError, match="gate failed"):
                    dx.extract_dti_tensor(str(tmp_path), "001", logger=MagicMock())
    finally:
        reset_path_manager()
    assert json.loads((m2m / "DTI_coregT1_qc.json").read_text())["passed"] is passes
    assert order == (["tensor", "advisories", ("report", ())] if passes else ["advisories", ("report", ("ncc_chain",))])
