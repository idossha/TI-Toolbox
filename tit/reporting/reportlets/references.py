"""
References reportlet for TI-Toolbox reports.

This module provides the default citations and references used across
TI-Toolbox reports.
"""

from typing import Any, Dict, List, Optional

from ..core.base import ReferencesReportlet


# Default TI-Toolbox references
DEFAULT_REFERENCES: List[Dict[str, str]] = [
    {
        "key": "ti",
        "citation": (
            "Grossman N, Bono D, Dedic N, Kodandaramaiah SB, Rudenko A, Suk HJ, "
            "Cassara AM, Neufeld E, Kuster N, Tsai LH, Bhardwaj R, Bhardwaj B. "
            "Noninvasive Deep Brain Stimulation via Temporally Interfering "
            "Electric Fields. Cell. 2017 Jun 1;169(6):1029-1041.e16."
        ),
        "doi": "10.1016/j.cell.2017.05.024",
    },
    {
        "key": "simnibs",
        "citation": (
            "Thielscher A, Antunes A, Saturnino GB. Field modeling for "
            "transcranial magnetic stimulation: A useful tool to understand "
            "the physiological effects of TMS? 2015 37th Annual International "
            "Conference of the IEEE Engineering in Medicine and Biology "
            "Society (EMBC). 2015 Aug;222-225."
        ),
        "doi": "10.1109/EMBC.2015.7318340",
    },
    {
        "key": "simnibs4",
        "citation": (
            "Saturnino GB, Puonti O, Nielsen JD, Antonenko D, Madsen KH, "
            "Thielscher A. SimNIBS 2.1: A Comprehensive Pipeline for "
            "Individualized Electric Field Modelling for Transcranial Brain "
            "Stimulation. In: Makarov S, Horner M, Noetscher G, editors. "
            "Brain and Human Body Modeling. Cham: Springer International "
            "Publishing; 2019. p. 3-25."
        ),
        "doi": "10.1007/978-3-030-21293-3_1",
    },
    {
        "key": "freesurfer",
        "citation": (
            "Fischl B. FreeSurfer. NeuroImage. 2012 Aug 15;62(2):774-81."
        ),
        "doi": "10.1016/j.neuroimage.2012.01.021",
    },
    {
        "key": "qsiprep",
        "citation": (
            "Cieslak M, Cook PA, He X, Yeh FC, Dhollander T, Adebimpe A, "
            "Aguirre GK, Bassett DS, Betzel RF, Bourque J, Cabral LM, "
            "Davatzikos C, Detre JA, Earl E, Elliott MA, Fadnavis S, Fair DA, "
            "Foran W, Fotiadis P, Garyfallidis E, Gur RE, Gur RC, "
            "Grayson DS, Gretchell A, Grimes TC, Harris A, Hopf JM, "
            "Humphries S, Jamison KW, Kahnt T, Keller AS, Kessler K, "
            "Kinnison J, Koenig A, Koller C, Koppelmans V, Kuceyeski A, "
            "Lashkari D, Li Q, Lowe AJ, Luck SJ, Ma S, Margulies DS, "
            "Marsland A, Marshall AT, McAllister DC, McMurray MS, Murty VP, "
            "Nebel MB, Newton AT, Nomi JS, Oathes DJ, Palmeri H, "
            "Parkes LM, Patriat R, Phan A, Piray P, Poldrack RA, Price M, "
            "Raznahan A, Roalf DR, Rohde GK, Rothlein D, Ryman SG, "
            "Salsman JM, Satterthwaite TD, Scheuer L, Schmitt JE, Schreiner MW, "
            "Shen X, Shultz S, Simmons WK, Sotiras A, Stampf TG, "
            "Sydnor VJ, Thompson PM, Thompson WK, Tunmer S, Turner BO, "
            "Uddin LQ, Vijayakumar N, Vogelstein JT, White T, Winkler AM, "
            "Xia CH, Xiao Y, Yang Y, Zamani Esfahlani F, Zhao Y, "
            "Zhou D, Craddock RC, Duff EP. "
            "QSIPrep: an integrative platform for preprocessing and "
            "reconstructing diffusion MRI data. Nat Methods. 2021 "
            "Jul;18(7):775-778."
        ),
        "doi": "10.1038/s41592-021-01185-5",
    },
    {
        "key": "dcm2niix",
        "citation": (
            "Li X, Morgan PS, Ashburner J, Smith J, Rorden C. The first step "
            "for neuroimaging data analysis: DICOM to NIfTI conversion. "
            "J Neurosci Methods. 2016 May 1;264:47-56."
        ),
        "doi": "10.1016/j.jneumeth.2016.03.001",
    },
    {
        "key": "charmed",
        "citation": (
            "Assaf Y, Basser PJ. Composite hindered and restricted model of "
            "diffusion (CHARMED) MR imaging of the human brain. NeuroImage. "
            "2005 Aug 1;27(1):48-58."
        ),
        "doi": "10.1016/j.neuroimage.2005.03.042",
    },
    {
        "key": "dti_conductivity",
        "citation": (
            "Rullmann M, Anwander A, Dannhauer M, Warfield SK, Duffy FH, "
            "Wolters CH. EEG source analysis of epileptiform activity using "
            "a 1 mm anisotropic hexahedra finite element head model. "
            "NeuroImage. 2009 Feb 1;44(2):399-410."
        ),
        "doi": "10.1016/j.neuroimage.2008.09.009",
    },
]


class TIToolboxReferencesReportlet(ReferencesReportlet):
    """
    Specialized references reportlet with TI-Toolbox default citations.

    Automatically includes relevant citations based on the pipeline
    components used.
    """

    def __init__(
        self,
        title: Optional[str] = None,
        include_defaults: bool = True,
        pipeline_components: Optional[List[str]] = None,
    ):
        """
        Initialize the TI-Toolbox references reportlet.

        Args:
            title: Section title
            include_defaults: Whether to include default TI-Toolbox refs
            pipeline_components: List of components used (to filter refs)
        """
        super().__init__(title=title or "References")

        self.pipeline_components = pipeline_components or []

        if include_defaults:
            self._add_default_references()

    def _add_default_references(self) -> None:
        """Add default references based on pipeline components."""
        # Always include TI and SimNIBS references
        core_refs = ["ti", "simnibs", "simnibs4"]

        # Add component-specific references
        component_ref_map = {
            "freesurfer": ["freesurfer"],
            "qsiprep": ["qsiprep"],
            "dcm2niix": ["dcm2niix"],
            "dti": ["charmed", "dti_conductivity"],
            "anisotropic": ["charmed", "dti_conductivity"],
        }

        refs_to_add = set(core_refs)
        for component in self.pipeline_components:
            component_lower = component.lower()
            if component_lower in component_ref_map:
                refs_to_add.update(component_ref_map[component_lower])

        # Add references
        for ref_data in DEFAULT_REFERENCES:
            if ref_data["key"] in refs_to_add:
                self.add_reference(
                    key=ref_data["key"],
                    citation=ref_data["citation"],
                    doi=ref_data.get("doi"),
                    url=ref_data.get("url"),
                )

    def add_default_reference(self, key: str) -> bool:
        """
        Add a default reference by key.

        Args:
            key: The reference key (e.g., 'freesurfer', 'qsiprep')

        Returns:
            True if reference was found and added, False otherwise
        """
        for ref_data in DEFAULT_REFERENCES:
            if ref_data["key"] == key:
                # Check if already added
                if not any(r["key"] == key for r in self.references):
                    self.add_reference(
                        key=ref_data["key"],
                        citation=ref_data["citation"],
                        doi=ref_data.get("doi"),
                        url=ref_data.get("url"),
                    )
                return True
        return False


def get_default_references() -> List[Dict[str, str]]:
    """
    Get the list of default TI-Toolbox references.

    Returns:
        List of reference dictionaries
    """
    return DEFAULT_REFERENCES.copy()


def get_reference_by_key(key: str) -> Optional[Dict[str, str]]:
    """
    Get a specific reference by its key.

    Args:
        key: The reference key

    Returns:
        Reference dictionary or None if not found
    """
    for ref in DEFAULT_REFERENCES:
        if ref["key"] == key:
            return ref.copy()
    return None
