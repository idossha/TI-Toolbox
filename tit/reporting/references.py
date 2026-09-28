"""The citations TI-Toolbox reports use, as data: one dict per paper.

``key`` is the stable id a generator cites by, ``label`` the visible tag (``[Puonti2020]``),
``citation`` the text and ``doi`` the link. ``tit.reporting.qc_rules`` cites rules by DOI, and every
such DOI must be here (``tests/test_reporting_dti_qc.py``). Pages collect what they cite with
:class:`tit.reporting.html.components.Cites`, so a page lists only what it cites; an entry no
report cites is deleted.
"""

DEFAULT_REFERENCES: list[dict[str, str]] = [
    # ==========================================================================
    # Core TI-Toolbox, TI & SimNIBS references
    # ==========================================================================
    {
        "key": "grossman2017_ti",
        "label": "Grossman2017",
        "citation": (
            "Grossman N, Bono D, Dedic N, Kodandaramaiah SB, Rudenko A, "
            "Suk HJ, Cassara AM, Neufeld E, Kuster N, Tsai LH, Pascual-Leone A, "
            "Boyden ES. Noninvasive deep brain stimulation via temporally "
            "interfering electric fields. Cell. 2017;169(6):1029-1041.e16."
        ),
        "doi": "10.1016/j.cell.2017.05.024",
    },
    {
        "key": "saturnino2019_simnibs21",
        "label": "Saturnino2019b",
        "citation": (
            "Saturnino GB, Puonti O, Nielsen JD, Antonenko D, Madsen KH, "
            "Thielscher A. SimNIBS 2.1: a comprehensive pipeline for "
            "individualized electric field modelling for transcranial brain "
            "stimulation. In: Makarov SN, Noetscher GM, Nummenmaa A, eds. "
            "Brain and Human Body Modeling. Springer; 2019."
        ),
        "doi": "10.1007/978-3-030-21293-3_1",
    },
    {
        "key": "puonti2020_charm",
        "label": "Puonti2020",
        "citation": (
            "Puonti O, Van Leemput K, Saturnino GB, Siebner HR, Madsen KH, "
            "Thielscher A. Accurate and robust whole-head segmentation from "
            "magnetic resonance images for individualized head modeling. "
            "NeuroImage. 2020;219:117044."
        ),
        "doi": "10.1016/j.neuroimage.2020.117044",
    },
    # ==========================================================================
    # Field strength, safety and dose (simulator and optimiser reports; DOIs
    # resolved with OpenAlex 2026-09-28)
    # ==========================================================================
    {
        "key": "rampersad2019_ti_humans",
        "label": "Rampersad2019",
        "citation": (
            "Rampersad S, Roig-Solvas B, Yarossi M, Kulkarni PP, Santarnecchi E, "
            "et al. Prospects for transcranial temporal interference stimulation "
            "in humans: a computational study. NeuroImage. 2019."
        ),
        "doi": "10.1016/j.neuroimage.2019.116124",
    },
    {
        "key": "huang2017_invivo_fields",
        "label": "Huang2017",
        "citation": (
            "Huang Y, Liu AA, Lafon B, Friedman D, Dayan M, et al. Measurements "
            "and models of electric fields in the in vivo human brain during "
            "transcranial electric stimulation. eLife. 2017;6:e18834."
        ),
        "doi": "10.7554/eLife.18834",
    },
    {
        "key": "bikson2016_tdcs_safety",
        "label": "Bikson2016",
        "citation": (
            "Bikson M, Grossman P, Thomas C, Zannou AL, Jiang J, et al. Safety of "
            "transcranial direct current stimulation: evidence based update 2016. "
            "Brain Stimulation. 2016."
        ),
        "doi": "10.1016/j.brs.2016.06.004",
    },
    {
        "key": "antal2017_tes_guidelines",
        "label": "Antal2017",
        "citation": (
            "Antal A, Alekseichuk I, Bikson M, Brockmöller J, Brunoni AR, et al. "
            "Low intensity transcranial electric stimulation: safety, ethical, "
            "legal regulatory and application guidelines. Clinical "
            "Neurophysiology. 2017."
        ),
        "doi": "10.1016/j.clinph.2017.06.001",
    },
    {
        "key": "cassara2025_tis_safety",
        "label": "Cassara2025",
        "citation": (
            "Cassarà AM, Newton T, Zhuang K, Regel SJ, Achermann P, et al. "
            "Recommendations for the safe application of temporal interference "
            "stimulation in the human brain part II: biophysics, dosimetry, and "
            "safety recommendations. Bioelectromagnetics. 2025."
        ),
        "doi": "10.1002/bem.22536",
    },
    {
        "key": "saturnino2019_accessibility",
        "label": "Saturnino2019c",
        "citation": (
            "Saturnino GB, Siebner HR, Thielscher A, Madsen KH. Accessibility of "
            "cortical regions to focal TES: dependence on spatial position, "
            "safety, and practical constraints. NeuroImage. 2019."
        ),
        "doi": "10.1016/j.neuroimage.2019.116183",
    },
    {
        "key": "peterchev2012_dose",
        "label": "Peterchev2012",
        "citation": (
            "Peterchev AV, Wagner TA, Miranda PC, Nitsche MA, Paulus W, et al. "
            "Fundamentals of transcranial electric and magnetic stimulation dose: "
            "definition, selection, and reporting practices. Brain Stimulation. "
            "2012."
        ),
        "doi": "10.1016/j.brs.2011.10.001",
    },
    # ==========================================================================
    # EEG electrode positioning
    # ==========================================================================
    {
        "key": "jurcak2007_eeg_positions",
        "label": "Jurcak2007",
        "citation": (
            "Jurcak V, Tsuzuki D, Dan I. 10/20, 10/10, and 10/5 systems "
            "revisited: their validity as relative head-surface-based "
            "positioning systems. NeuroImage. 2007;34(4):1600-1611."
        ),
        "doi": "10.1016/j.neuroimage.2006.09.024",
    },
    # ==========================================================================
    # Preprocessing & data format references
    # ==========================================================================
    {
        "key": "cieslak2021_qsiprep",
        "label": "Cieslak2021",
        "citation": (
            "Cieslak M, et al. QSIPrep: an integrative platform for "
            "preprocessing and reconstructing diffusion MRI data. Nature "
            "Methods. 2021;18(7):775-778."
        ),
        "doi": "10.1038/s41592-021-01185-5",
    },
    # ==========================================================================
    # Workflow/reporting references
    # ==========================================================================
    {
        "key": "gorgolewski2011_nipype",
        "label": "Nipype2011",
        "citation": (
            "Gorgolewski K, Burns CD, Madison C, Clark D, Halchenko YO, "
            "Waskom ML, Ghosh SS. Nipype: a flexible, lightweight and "
            "extensible neuroimaging data processing framework in Python. "
            "Frontiers in Neuroinformatics. 2011;5:13."
        ),
        "doi": "10.3389/fninf.2011.00013",
    },
    # ==========================================================================
    # Flex-search / optimization references
    # ==========================================================================
    {
        "key": "weise2025_leadfield_free",
        "label": "Weise2025",
        "citation": (
            "Weise K, Madsen KH, Worbs T, Knosche TR, Korshoj A, Thielscher A. "
            "A leadfield-free optimization framework for transcranially applied "
            "electric currents. Computers in Biology and Medicine. 2025."
        ),
        "doi": "10.1016/j.compbiomed.2025.110648",
    },
    # ==========================================================================
    # DTI / Anisotropic conductivity references
    # ==========================================================================
    {
        "key": "rullmann2009_dti_conductivity",
        "label": "Rullmann2009",
        "citation": (
            "Rullmann M, Anwander A, Dannhauer M, Warfield SK, Duffy FH, "
            "Wolters CH. EEG source analysis of epileptiform activity using "
            "a 1 mm anisotropic hexahedra finite element head model. "
            "NeuroImage. 2009;44(2):399-410."
        ),
        "doi": "10.1016/j.neuroimage.2008.09.009",
    },
    {
        "key": "tuch2001_conductivity",
        "label": "Tuch2001",
        "citation": (
            "Tuch DS, Wedeen VJ, Dale AM, George JS, Belliveau JW. Conductivity "
            "tensor mapping of the human brain using diffusion tensor MRI. "
            "Proceedings of the National Academy of Sciences. 2001;98(20):11697-11701."
        ),
        "doi": "10.1073/pnas.171473898",
    },
    {
        "key": "opitz2011_tissue_efield",
        "label": "Opitz2011",
        "citation": (
            "Opitz A, Windhoff M, Heidemann RM, Turner R, Thielscher A. How the "
            "brain tissue shapes the electric field induced by transcranial "
            "magnetic stimulation. NeuroImage. 2011;58(3):849-859."
        ),
        "doi": "10.1016/j.neuroimage.2011.06.069",
    },
    {
        "key": "garyfallidis2014_dipy",
        "label": "Garyfallidis2014",
        "citation": (
            "Garyfallidis E, Brett M, Amirbekian B, Rokem A, van der Walt S, "
            "Descoteaux M, Nimmo-Smith I, Dipy Contributors. Dipy, a library for "
            "the analysis of diffusion MRI data. Frontiers in Neuroinformatics. "
            "2014;8:8."
        ),
        "doi": "10.3389/fninf.2014.00008",
    },
    {
        "key": "veraart2016_mppca",
        "label": "Veraart2016",
        "citation": (
            "Veraart J, Novikov DS, Christiaens D, Ades-Aron B, Sijbers J, "
            "Fieremans E. Denoising of diffusion MRI using random matrix theory. "
            "NeuroImage. 2016;142:394-406."
        ),
        "doi": "10.1016/j.neuroimage.2016.08.016",
    },
    {
        "key": "kellner2016_gibbs",
        "label": "Kellner2016",
        "citation": (
            "Kellner E, Dhital B, Kiselev VG, Reisert M. Gibbs-ringing artifact "
            "removal based on local subvoxel-shifts. Magnetic Resonance in "
            "Medicine. 2016;76(5):1574-1581."
        ),
        "doi": "10.1002/mrm.26054",
    },
    {
        "key": "andersson2016_eddy",
        "label": "Andersson2016",
        "citation": (
            "Andersson JLR, Sotiropoulos SN. An integrated approach to correction "
            "for off-resonance effects and subject movement in diffusion MR "
            "imaging. NeuroImage. 2016;125:1063-1078."
        ),
        "doi": "10.1016/j.neuroimage.2015.10.019",
    },
    {
        "key": "tournier2019_mrtrix3",
        "label": "Tournier2019",
        "citation": (
            "Tournier J-D, Smith R, Raffelt D, Tabbara R, Dhollander T, Pietsch M, "
            "Christiaens D, Jeurissen B, Yeh C-H, Connelly A. MRtrix3: a fast, "
            "flexible and open software framework for medical image processing "
            "and visualisation. NeuroImage. 2019;202:116137."
        ),
        "doi": "10.1016/j.neuroimage.2019.116137",
    },
    {
        "key": "jeurissen2014_gradient_flip",
        "label": "Jeurissen2014",
        "citation": (
            "Jeurissen B, Leemans A, Sijbers J. Automated correction of "
            "improperly rotated diffusion gradient orientations in diffusion "
            "weighted MRI. Medical Image Analysis. 2014;18(7):953-962."
        ),
        "doi": "10.1016/j.media.2014.05.012",
    },
    # ==========================================================================
    # DTI quality-control rules (tit/reporting/qc_rules.py); DOIs checked
    # against OpenAlex 2026-09-28
    # ==========================================================================
    {
        "key": "pierpaoli1996_dti",
        "label": "Pierpaoli1996",
        "citation": (
            "Pierpaoli C, Jezzard P, Basser PJ, Barnett A, Di Chiro G. Diffusion "
            "tensor MR imaging of the human brain. Radiology. 1996;201(3):637-648."
        ),
        "doi": "10.1148/radiology.201.3.8939209",
    },
    {
        "key": "cox2016_ukb_white_matter",
        "label": "Cox2016",
        "citation": (
            "Cox SR, Ritchie SJ, Tucker-Drob EM, Liewald DC, Hagenaars SP, Davies G, "
            "Wardlaw JM, Gale CR, Bastin ME, Deary IJ. Ageing and brain white matter "
            "structure in 3,513 UK Biobank participants. Nature Communications. "
            "2016;7:13629."
        ),
        "doi": "10.1038/ncomms13629",
    },
    {
        "key": "jezzard1995_epi_distortion",
        "label": "Jezzard1995",
        "citation": (
            "Jezzard P, Balaban RS. Correction for geometric distortion in echo "
            "planar images from B0 field variations. Magnetic Resonance in "
            "Medicine. 1995;34(1):65-73."
        ),
        "doi": "10.1002/mrm.1910340111",
    },
    {
        "key": "schilling2019_btable",
        "label": "Schilling2019",
        "citation": (
            "Schilling KG, Yeh F-C, Nath V, Hansen C, Williams O, Resnick S, "
            "Anderson AW, Landman BA. A fiber coherence index for quality control "
            "of B-table orientation in diffusion MRI scans. Magnetic Resonance "
            "Imaging. 2019;58:82-89."
        ),
        "doi": "10.1016/j.mri.2019.01.018",
    },
    {
        "key": "roalf2016_dti_qa",
        "label": "Roalf2016",
        "citation": (
            "Roalf DR, Quarmley M, Elliott MA, Satterthwaite TD, Vandekar SN, "
            "Ruparel K, et al. The impact of quality assurance assessment on "
            "diffusion tensor imaging outcomes in a large-scale population-based "
            "cohort. NeuroImage. 2016;125:903-919."
        ),
        "doi": "10.1016/j.neuroimage.2015.10.068",
    },
    {
        "key": "yendiki2014_motion",
        "label": "Yendiki2014",
        "citation": (
            "Yendiki A, Koldewyn K, Kakunoori S, Kanwisher N, Fischl B. Spurious "
            "group differences due to head motion in a diffusion MRI study. "
            "NeuroImage. 2014;88:79-90."
        ),
        "doi": "10.1016/j.neuroimage.2013.11.027",
    },
    {
        "key": "westlye2010_lifespan",
        "label": "Westlye2010",
        "citation": (
            "Westlye LT, Walhovd KB, Dale AM, Bjørnerud A, Due-Tønnessen P, Engvig A, "
            "et al. Life-span changes of the human brain white matter: diffusion "
            "tensor imaging (DTI) and volumetry. Cerebral Cortex. "
            "2010;20(9):2055-2068."
        ),
        "doi": "10.1093/cercor/bhp280",
    },
    {
        "key": "lebel2012_lifespan",
        "label": "Lebel2012",
        "citation": (
            "Lebel C, Gee M, Camicioli R, Wieler M, Martin W, Beaulieu C. Diffusion "
            "tensor imaging of white matter tract evolution over the lifespan. "
            "NeuroImage. 2012;60(1):340-352."
        ),
        "doi": "10.1016/j.neuroimage.2011.11.094",
    },
    {
        "key": "yeh2019_differential_tractography",
        "label": "Yeh2019",
        "citation": (
            "Yeh F-C, Zaydan IM, Suski VR, Lacomis D, Richardson RM, Maroon JC, "
            "Barrios-Martinez J. Differential tractography as a track-based "
            "biomarker for neuronal injury. NeuroImage. 2019;202:116131."
        ),
        "doi": "10.1016/j.neuroimage.2019.116131",
    },
    {
        "key": "andersson2016_outliers",
        "label": "Andersson2016b",
        "citation": (
            "Andersson JLR, Graham MS, Zsoldos E, Sotiropoulos SN. Incorporating "
            "outlier detection and replacement into a non-parametric framework for "
            "movement and distortion correction of diffusion MR images. NeuroImage. "
            "2016;141:556-572."
        ),
        "doi": "10.1016/j.neuroimage.2016.06.058",
    },
    {
        "key": "esteban2019_fmriprep",
        "label": "Esteban2019",
        "citation": (
            "Esteban O, Markiewicz CJ, Blair RW, Moodie CA, Isik AI, Erramuzpe A, "
            "et al. fMRIPrep: a robust preprocessing pipeline for functional MRI. "
            "Nature Methods. 2019;16(1):111-116."
        ),
        "doi": "10.1038/s41592-018-0235-4",
    },
]


def get_reference_by_key(key: str) -> dict[str, str] | None:
    """The reference with this stable key or visible label (any case), or ``None``."""
    k = str(key).strip().lower()
    return next(
        (
            ref.copy()
            for ref in DEFAULT_REFERENCES
            if k in (ref["key"].lower(), ref.get("label", "").lower())
        ),
        None,
    )


def get_reference_by_doi(doi: str) -> dict | None:
    """The reference with this DOI, or ``None``."""
    return next(
        (ref.copy() for ref in DEFAULT_REFERENCES if ref.get("doi") == doi), None
    )
