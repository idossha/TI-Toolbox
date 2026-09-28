"""The citations TI-Toolbox reports use, as data: one dict per paper.

``key`` is the stable id a generator cites by, ``label`` the visible tag (``[Haber2026]``),
``citation`` the text and ``doi`` the link. ``tit.reporting.qc_rules`` cites rules by DOI, and every
such DOI must be here (``tests/test_reporting_dti_qc.py``). Pages collect what they cite with
:class:`tit.reporting.html.components.Cites`.
"""

DEFAULT_REFERENCES: list[dict[str, str]] = [
    # ==========================================================================
    # Core TI-Toolbox, TI & SimNIBS references
    # ==========================================================================
    {
        "key": "haber2026_titoolbox",
        "label": "Haber2026",
        "citation": (
            "Haber I, Jackson A, Thielscher A, Hai A, Tononi G. TI-Toolbox: "
            "an open-source software for temporal interference stimulation "
            "research. Brain Stimulation. 2026."
        ),
        "doi": "10.1016/j.brs.2025.103016",
    },
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
        "key": "saturnino2019_simnibs_fem",
        "label": "Saturnino2019",
        "citation": (
            "Saturnino GB, Madsen KH, Thielscher A. Electric field "
            "simulations for transcranial brain stimulation using FEM: an "
            "efficient implementation and error analysis. Journal of Neural "
            "Engineering. 2019;16(6):066006."
        ),
        "doi": "10.1088/1741-2552/ab41ba",
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
        "key": "thielscher2015_simnibs_tms",
        "label": "Thielscher2015",
        "citation": (
            "Thielscher A, Antunes A, Saturnino GB. Field modeling for "
            "transcranial magnetic stimulation: a useful tool to understand "
            "the physiological effects of TMS? In: 2015 37th Annual "
            "International Conference of the IEEE Engineering in Medicine "
            "and Biology Society (EMBC). Milan: IEEE; 2015. p. 222-225."
        ),
        "doi": "10.1109/EMBC.2015.7318340",
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
    # Simulation-specific references
    # ==========================================================================
    {
        "key": "botzanowski2025_mti",
        "label": "Botzanowski2025",
        "citation": (
            "Botzanowski B, et al. Focal control of non-invasive deep brain "
            "stimulation using multipolar temporal interference. Bioelectronic "
            "Medicine. 2025;11(1):7."
        ),
        "doi": "10.1186/s42234-025-00169-6",
    },
    {
        "key": "saturnino2015_electrodes",
        "label": "Saturnino2015",
        "citation": (
            "Saturnino GB, Antunes A, Thielscher A. On the importance of "
            "electrode parameters for shaping electric field patterns "
            "generated by tDCS. NeuroImage. 2015;120:25-35."
        ),
        "doi": "10.1016/j.neuroimage.2015.06.067",
    },
    {
        "key": "gaugain2023_quasistatic",
        "label": "Gaugain2023",
        "citation": (
            "Gaugain G, et al. Quasi-static approximation error of electric "
            "field analysis for transcranial current stimulation. Journal of "
            "Neural Engineering. 2023;20(1):016027."
        ),
        "doi": "10.1088/1741-2552/acb14d",
    },
    {
        "key": "opitz2015_tdcs_determinants",
        "label": "Opitz2015",
        "citation": (
            "Opitz A, Paulus W, Will S, Antunes A, Thielscher A. Determinants "
            "of the electric field during transcranial direct current "
            "stimulation. NeuroImage. 2015;109:140-150."
        ),
        "doi": "10.1016/j.neuroimage.2015.01.033",
    },
    # ==========================================================================
    # Atlas references
    # ==========================================================================
    {
        "key": "mazziotta2001_icbm",
        "label": "Mazziotta2001",
        "citation": (
            "Mazziotta J, et al. A probabilistic atlas and reference system "
            "for the human brain: International Consortium for Brain Mapping "
            "(ICBM). Philosophical Transactions of the Royal Society B. "
            "2001;356(1412):1293-1322."
        ),
        "doi": "10.1098/rstb.2001.0915",
    },
    {
        "key": "glasser2016_hcp_mmp",
        "label": "Glasser2016",
        "citation": (
            "Glasser MF, et al. A multi-modal parcellation of human cerebral "
            "cortex. Nature. 2016;536(7615):171-178."
        ),
        "doi": "10.1038/nature18933",
    },
    {
        "key": "destrieux2010_atlas",
        "label": "Destrieux2010",
        "citation": (
            "Destrieux C, Fischl B, Dale A, Halgren E. Automatic parcellation "
            "of human cortical gyri and sulci using standard anatomical "
            "nomenclature. NeuroImage. 2010;53(1):1-15."
        ),
        "doi": "10.1016/j.neuroimage.2010.06.010",
    },
    {
        "key": "alexander2019_dkt",
        "label": "Alexander2019",
        "citation": (
            "Alexander B, et al. Desikan-Killiany-Tourville atlas compatible "
            "version of M-CRIB neonatal parcellated whole brain atlas: the "
            "M-CRIB 2.0. Frontiers in Neuroscience. 2019;13:34."
        ),
        "doi": "10.3389/fnins.2019.00034",
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
    {
        "key": "egi_sensor_nets",
        "label": "EGI Sensor Nets",
        "citation": "Geodesic Sensor Nets. Electrical Geodesics, Inc.",
        "url": "https://www.egi.com/clinical-division/geodesic-sensor-nets",
    },
    # ==========================================================================
    # Preprocessing & data format references
    # ==========================================================================
    {
        "key": "fischl2012_freesurfer",
        "label": "Fischl2012",
        "citation": "Fischl B. FreeSurfer. NeuroImage. 2012;62(2):774-781.",
        "doi": "10.1016/j.neuroimage.2012.01.021",
    },
    {
        "key": "bids2016",
        "label": "BIDS2016",
        "citation": (
            "Gorgolewski KJ, et al. The brain imaging data structure, a "
            "format for organizing and describing outputs of neuroimaging "
            "experiments. Scientific Data. 2016;3:160044."
        ),
        "doi": "10.1038/sdata.2016.44",
    },
    {
        "key": "gorgolewski2017_bids_apps",
        "label": "BIDSApps2017",
        "citation": (
            "Gorgolewski KJ, et al. BIDS apps: improving ease of use, "
            "accessibility, and reproducibility of neuroimaging data analysis "
            "methods. PLoS Computational Biology. 2017;13(3):e1005209."
        ),
        "doi": "10.1371/journal.pcbi.1005209",
    },
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
    {
        "key": "li2016_dcm2niix",
        "label": "Li2016",
        "citation": (
            "Li X, Morgan PS, Ashburner J, Smith J, Rorden C. The first step "
            "for neuroimaging data analysis: DICOM to NIfTI conversion. "
            "Journal of Neuroscience Methods. 2016;264:47-56."
        ),
        "doi": "10.1016/j.jneumeth.2016.03.001",
    },
    # ==========================================================================
    # Workflow/reporting references
    # ==========================================================================
    {
        "key": "abraham2014_nilearn",
        "label": "Nilearn2014",
        "citation": (
            "Abraham A, et al. Machine learning for neuroimaging with scikit-learn. "
            "Frontiers in Neuroinformatics. 2014;8:14."
        ),
        "doi": "10.3389/fninf.2014.00014",
    },
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
        "key": "assaf2005_charmed",
        "label": "Assaf2005",
        "citation": (
            "Assaf Y, Basser PJ. Composite hindered and restricted model of "
            "diffusion (CHARMED) MR imaging of the human brain. NeuroImage. "
            "2005;27(1):48-58."
        ),
        "doi": "10.1016/j.neuroimage.2005.03.042",
    },
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
    # ==========================================================================
    # Meshing & visualization
    # ==========================================================================
    {
        "key": "geuzaine2009_gmsh",
        "label": "Geuzaine2009",
        "citation": (
            "Geuzaine C, Remacle JF. Gmsh: a 3-D finite element mesh "
            "generator with built-in pre- and post-processing facilities. "
            "International Journal for Numerical Methods in Engineering. "
            "2009;79(11):1309-1331."
        ),
        "doi": "10.1002/nme.2579",
    },
    {
        "key": "blender",
        "label": "Blender",
        "citation": "Blender - Free and Open 3D Creation Software.",
        "url": "https://github.com/blender/blender",
    },
]

# Backwards-compatible aliases accepted by add_default_reference/get_reference_by_key.


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
