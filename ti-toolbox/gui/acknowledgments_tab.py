#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Acknowledgments Tab for TI-Toolbox GUI
This module provides an acknowledgments tab to properly cite all tools and resources used.
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt

class AcknowledgmentsTab(QtWidgets.QWidget):
    """Acknowledgments tab for TI-Toolbox GUI."""
    
    def __init__(self, parent=None):
        super(AcknowledgmentsTab, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface for the acknowledgments tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title_label = QtWidgets.QLabel("<h1>Acknowledgments</h1>")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Description
        description = QtWidgets.QLabel(
            "<p>TI-Toolbox relies on several open-source tools and frameworks. "
            "We are grateful to the developers of these resources and acknowledge their contributions below.</p>"
        )
        description.setWordWrap(True)
        description.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(description)
        
        # Create a scroll area for the content
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        
        # Add all the acknowledgment sections
        self.add_acknowledgment_section(
            scroll_layout, 
            "TI-Toolbox",
            "Haber I, Jackson A, Thielscher A, Hai A, Tononi G. Temporal Interference Toolbox: A comprehensive pipeline for transcranial electrical stimulation optimization. bioRxiv 2025.10.06.680781; https://doi.org/10.1101/2025.10.06.680781."
        )

        self.add_acknowledgment_section(
            scroll_layout, 
            "SimNIBS CHARM Segmentation Pipeline",
            "Puonti O, Van Leemput K, Saturnino GB, Siebner HR, Madsen KH, Thielscher A. (2020). Accurate and robust whole-head segmentation from magnetic resonance images for individualized head modeling. Neuroimage, 219:117044."
        )

        self.add_acknowledgment_section(
            scroll_layout, 
            "Flex-Search Optimization Algorithm",
            "Weise K, Madsen KH, Worbs T, Knösche TR, Korshøj A, Thielscher A, A Leadfield-Free Optimization Framework for Transcranially Applied Electric Currents, bioRxiv 10.1101/2024.12.18.629095"
        )

        self.add_acknowledgment_section(
            scroll_layout, 
            "MOVEA Optimization Algorithm",
            "Wang, Kexin Lou, Zeming Liu, Pengfei Wei, Quanying Liu,Multi-objective optimization via evolutionary algorithm (MOVEA) for high-definition transcranial electrical stimulation of the human brain,NeuroImage, https://doi.org/10.1016/j.neuroimage.2023.120331."
        )
        
        self.add_acknowledgment_section(
            scroll_layout, 
            "Noninvasive Deep Brain Stimulation via Temporally Interfering Electric Fields",
            "Grossman N, Bono D, Dedic N, Kodandaramaiah SB, Rudenko A, Suk HJ, Cassara AM, Neufeld E, Kuster N, Tsai LH, Pascual-Leone A, Boyden ES. Noninvasive Deep Brain Stimulation via Temporally Interfering Electric Fields. Cell. 2017 Jun 1;169(6):1029-1041.e16. doi: 10.1016/j.cell.2017.05.024. PMID: 28575667; PMCID: PMC5520675."
        )
        
        self.add_acknowledgment_section(
            scroll_layout, 
            "FreeSurfer",
            "Fischl B. FreeSurfer. Neuroimage. 2012 Aug 15;62(2):774-81. https://doi.org/10.1016/j.neuroimage.2012.01.021."
        )
        
        self.add_acknowledgment_section(
            scroll_layout, 
            "FSL",
            "M.W. Woolrich, S. Jbabdi, B. Patenaude, M. Chappell, S. Makni, T. Behrens, C. Beckmann, M. Jenkinson, S.M. Smith. Bayesian analysis of neuroimaging data in FSL. NeuroImage, 45:S173-86, 2009<br><br>"
            "S.M. Smith, M. Jenkinson, M.W. Woolrich, C.F. Beckmann, T.E.J. Behrens, H. Johansen-Berg, P.R. Bannister, M. De Luca, I. Drobnjak, D.E. Flitney, R. Niazy, J. Saunders, J. Vickers, Y. Zhang, N. De Stefano, J.M. Brady, and P.M. Matthews. Advances in functional and structural MR image analysis and implementation as FSL. NeuroImage, 23(S1):208-19, 2004<br><br>"
            "M. Jenkinson, C.F. Beckmann, T.E. Behrens, M.W. Woolrich, S.M. Smith. FSL. NeuroImage, 62:782-90, 2012"
        )
        
        self.add_acknowledgment_section(
            scroll_layout, 
            "dcm2niix",
            "Li X, Morgan PS, Ashburner J, Smith J, Rorden C (2016) The first step for neuroimaging data analysis: DICOM to NIfTI conversion. J Neurosci Methods. 264:47-56. doi: 10.1016/j.jneumeth.2016.03.001. PMID: 26945974"
        )
        
        self.add_acknowledgment_section(
            scroll_layout, 
            "BIDS",
            "Gorgolewski, K., Auer, T., Calhoun, V. et al. The brain imaging data structure, a format for organizing and describing outputs of neuroimaging experiments. Sci Data 3, 160044 (2016). https://doi.org/10.1038/sdata.2016.44"
        )
        
        self.add_acknowledgment_section(
            scroll_layout, 
            "Docker",
            "Merkel, D. (2014). Docker: lightweight Linux containers for consistent development and deployment. Linux Journal, 2014(239), Article 2."
        )
        
        self.add_acknowledgment_section(
            scroll_layout, 
            "Gmsh",
            "C. Geuzaine and J.-F. Remacle. Gmsh: a three-dimensional finite element mesh generator with built-in pre- and post-processing facilities. International Journal for Numerical Methods in Engineering 79(11), pp. 1309-1331, 2009."
        )
        
        # Add a note at the bottom about missing acknowledgments
        note_label = QtWidgets.QLabel(
            "<p><i>If you're using TI-Toolbox in academic work, please cite the appropriate references above.</i></p>"
        )
        note_label.setWordWrap(True)
        note_label.setAlignment(QtCore.Qt.AlignCenter)
        scroll_layout.addWidget(note_label)
        
        # Add some stretching at the bottom
        scroll_layout.addStretch()
        
        # Set the scroll content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
    def add_acknowledgment_section(self, layout, title, content):
        """Add a section to the acknowledgments layout."""
        # Create a group box for this acknowledgment
        group_box = QtWidgets.QGroupBox(title)
        group_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        
        group_layout = QtWidgets.QVBoxLayout(group_box)
        
        # Content label
        content_label = QtWidgets.QLabel(content)
        content_label.setWordWrap(True)
        content_label.setOpenExternalLinks(True)
        content_label.setTextFormat(QtCore.Qt.RichText)
        group_layout.addWidget(content_label)
        
        # Add the group to the main layout
        layout.addWidget(group_box) 
