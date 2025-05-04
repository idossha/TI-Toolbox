#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Help Tab for TI-CSC-2.0 GUI
This module provides a unified help tab for all TI-CSC-2.0 tools.
"""

from PyQt5 import QtWidgets, QtCore, QtGui

class HelpTab(QtWidgets.QWidget):
    """Unified help tab for TI-CSC-2.0 GUI."""
    
    def __init__(self, parent=None):
        super(HelpTab, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface for the help tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Introduction text
        intro_label = QtWidgets.QLabel("<h1>TI-CSC-2.0 Help Center</h1>")
        intro_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(intro_label)
        
        description_label = QtWidgets.QLabel(
            "<p>Welcome to the TI-CSC-2.0 Toolbox help center. "
            "This tab provides comprehensive information about all the tools available in this application.</p>"
        )
        description_label.setWordWrap(True)
        description_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(description_label)
        
        # Create a scroll area for the help content
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        # Create a widget to hold the help content
        help_widget = QtWidgets.QWidget()
        help_layout = QtWidgets.QVBoxLayout(help_widget)
        
        # Add sections from all tools
        self.add_pre_processing_help(help_layout)
        self.add_simulator_help(help_layout)
        self.add_flex_search_help(help_layout)
        self.add_nifti_viewer_help(help_layout)
        
        # Add general usage tips
        self.add_general_usage_tips(help_layout)
        
        # Set the help widget as the scroll area's widget
        scroll_area.setWidget(help_widget)
        main_layout.addWidget(scroll_area)
    
    def add_section(self, layout, title, content):
        """Add a section to the help layout."""
        # Section title
        title_label = QtWidgets.QLabel(f"<h2>{title}</h2>")
        title_label.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(title_label)
        
        # Section content
        content_label = QtWidgets.QLabel(content)
        content_label.setTextFormat(QtCore.Qt.RichText)
        content_label.setWordWrap(True)
        layout.addWidget(content_label)
        
        # Add separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator)
    
    def add_pre_processing_help(self, layout):
        """Add Pre-processing help content."""
        # Add header for the Pre-processing tool
        header_label = QtWidgets.QLabel("<h1>Pre-processing Tool</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Pre-processing sections
        sections = [
            {
                "title": "What is Pre-processing?",
                "content": (
                    "Pre-processing is the first step in preparing neuroimaging data for TI-CSC simulations. "
                    "It involves converting DICOM images to NIfTI format, creating head models using FreeSurfer "
                    "and SimNIBS, and preparing the data for subsequent simulation and analysis."
                )
            },
            {
                "title": "Subject Selection",
                "content": (
                    "<b>Multiple Subject Selection:</b><br>"
                    "- Select one or more subjects from the list using Ctrl+click or Shift+click<br>"
                    "- The 'Refresh List' button updates the subject list from the project directory<br><br>"
                    
                    "Make sure you follow the required BIDS directory structure<br>"
                )
            },
            {
                "title": "Processing Options",
                "content": (
                    "<b>Convert DICOM files to NIfTI:</b><br>"
                    "- Converts medical DICOM images into NIfTI format (.nii or .nii.gz)<br>"
                    "- Requires raw DICOM files in the subject's /anat/raw/ directory<br>"
                    "- Automatically identifies T1 and T2 images based on metadata in the .json file<br><br>"
                    
                    "<b>Run FreeSurfer recon-all:</b><br>"
                    "- Performs structural MRI analysis using FreeSurfer's recon-all<br>"
                    "- Creates cortical surface models and anatomical parcellations<br>"
                    "- This is a computationally intensive step that can take several hours<br><br>"
                    
                    "<b>Run FreeSurfer reconstruction in parallel:</b><br>"
                    "- Uses GNU Parallel to accelerate processing when handling multiple subjects<br>"
                    "- Only applies when 'Run FreeSurfer recon-all' is selected<br>"
                    "- This is still experimental and have not been tested extensively<br><br>"

                    "<b>Create SimNIBS m2m folder:</b><br>"
                    "- Runs the SimNIBS charm tool to create subject-specific head models<br>"
                    "- Generates meshes necessary for electromagnetic field simulations<br>"
                    "- Creates the m2m_[SUBJECT_ID] directory in the SimNIBS folder<br><br>"
                    
                    "<b>Run in quiet mode:</b><br>"
                    "- Suppresses detailed output during processing<br>"
                )
            },
            {
                "title": "Processing Workflow",
                "content": (
                    "The typical pre-processing workflow follows these steps:<br><br>"
                    
                    "1. <b>DICOM to NIfTI Conversion:</b><br>"
                    "   - Raw DICOM files are identified and converted to NIfTI format<br>"
                    "   - T1 and T2 images are detected and properly named<br><br>"
                    
                    "2. <b>FreeSurfer Reconstruction:</b><br>"
                    "   - T1 images and optionally T2 images are processed using FreeSurfer's recon-all<br>"
                    "   - Creates cortical surface models and segmentation of brain structures<br><br>"
                    
                    "3. <b>SimNIBS Head Model Creation:</b><br>"
                    "   - Uses the SimNIBS charm tool to create realistic head models<br>"
                    "   - Generates mesh files for FEM simulations<br><br>"
                    
                    "Once pre-processing is complete, the subject data is ready for TI-CSC simulations."
                )
            },
            {
                "title": "Tips and Troubleshooting",
                "content": (
                    "- Ensure that raw DICOM files are properly organized in the subject's /anat/raw/ directory<br>"
                    "- T1-weighted MRI scans are required for FreeSurfer reconstruction<br>"
                    "- T2-weighted MRI scans are optional but improve head model quality<br>"
                    "- When processing multiple subjects, consider using parallel processing<br>"
                    "- The Console Output window shows real-time progress and any error messages<br>"
                    "- If processing fails, check the console output for specific error messages<br>"
                    "- The Stop button can be used to terminate processing, but may leave files in an inconsistent state"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])
    
    def add_simulator_help(self, layout):
        """Add Simulator help content."""
        # Add header for the Simulator tool
        header_label = QtWidgets.QLabel("<h1>Simulator Tool</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Simulator sections
        sections = [
            {
                "title": "What is the TI-CSC Simulator?",
                "content": (
                    "The TI-CSC Simulator performs computational simulations of Temporal Interference (TI) stimulation "
                    "using finite element modeling (FEM). It calculates electric field distributions in subject-specific "
                    "head models for different electrode configurations and stimulation parameters."
                    "It uses SimNIBS' TI module to simulate the electric field distribution based on Grossmna's equation from the 2017 paper."
                )
            },
            {
                "title": "Subject Selection",
                "content": (
                    "- Select one or more subjects from the list using Ctrl+click or Shift+click<br>"
                    "- Each subject must have been pre-processed with a SimNIBS head model<br>"
                    "- The subject list automatically populates with available subjects<br>"
                    "- Use the 'Refresh List' button to update the subject list"
                )
            },
            {
                "title": "Montage Selection",
                "content": (
                    "<b>Predefined Montages:</b><br>"
                    "- Choose from a list of predefined electrode configurations<br>"
                    "- The montage list is populated based on the selected simulation mode<br>"
                    "- Multiple montages can be selected for batch processing<br><br>"
                    
                    "<b>Custom Montage:</b><br>"
                    "- Use the 'Add Custom Montage' button to create new electrode configurations<br>"
                    "- For Multipolar mode, specify two pairs of electrode positions<br>"
                    "- For Unipolar mode, specify anode and cathode positions<br>"
                    "- Position names should match the desired EEG net"
                )
            },
            {
                "title": "Simulation Parameters",
                "content": (
                    "<b>Simulation Type:</b><br>"
                    "- <b>Standard isotropic:</b> Uses default conductivity values for all tissue types<br>"
                    "- <b>anisotropic:</b> Takes into account the anisotropy of the tissue based on a DTI scan.<br><br>"
                    
                    "<b>Simulation Mode:</b><br>"
                    "- <b>Unipolar:</b> Uses two pairs for conventional TI stimulation<br><br>"
                    "- <b>Multipolar:</b> Uses four pairs of electrodes for mTI stimulation<br>"
                    
                    "<b>Electrode Parameters:</b><br>"
                    "- <b>Shape:</b> Rectangular (pad) or circular electrodes<br>"
                    "- <b>Dimensions:</b> Size in millimeters (width,height for rectangular; diameter for circular)<br>"
                    "- <b>Thickness:</b> Electrode thickness in millimeters<br>"
                    "- <b>Current:</b> Stimulation intensity in milliamperes (mA)"
                )
            },
            {
                "title": "Simulation Process",
                "content": (
                    "1. The simulator creates FEM models for each electrode configuration<br>"
                    "2. It solves the electric field equations using SimNIBS<br>"
                    "3. For TI stimulation, it calculates the amplitude-modulated field<br>"
                    "4. Results are stored in the subject's SimNIBS directory<br><br>"
                    
                    "Simulation progress and status messages are displayed in the console window."
                )
            },
            {
                "title": "Output Files",
                "content": (
                    "Simulation results are saved in:<br>"
                    "[PROJECT_DIR]/[SUBJECT_ID]/SimNIBS/Simulations/[montage_name]/<br><br>"
                    
                    "Output includes:<br>"
                    "- Electric field distributions (.msh and .nii.gz formats)<br>"
                    "- Electrode positions and parameters<br>"
                    "- Log files with simulation parameters<br>"
                    "- Visualization-ready files compatible with SimNIBS GUI and NIfTI viewers"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])
    
    def add_flex_search_help(self, layout):
        """Add Flex Search help content."""
        # Add header for the Flex Search tool
        header_label = QtWidgets.QLabel("<h1>Flex Search Tool</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Flex Search sections
        sections = [
            {
                "title": "What is Flex Search?",
                "content": (
                    "Flex Search is an electrode position optimization tool for temporal interference (TI) "
                    "stimulation. It finds the optimal positions for two pairs of electrodes to target a "
                    "specific region of interest (ROI) in the brain."
                )
            },
            {
                "title": "Optimization Parameters",
                "content": (
                    "<b>Subject Selection:</b><br>"
                    "- Choose a subject ID from the dropdown menu<br><br>"
                    
                    "<b>Optimization Goal:</b><br>"
                    "- <b>Maximize field in target ROI:</b> Finds electrode positions that maximize the TI field strength in the target region<br>"
                    "- <b>Maximize normal component of field in ROI:</b> Optimizes for field components perpendicular to the cortical surface<br>"
                    "- <b>Maximize focality:</b> Maximizes field in the target region while minimizing it elsewhere<br><br>"
                    
                    "<b>Post-processing Method:</b><br>"
                    "- <b>Maximum TI field (max_TI):</b> Uses the maximum TI field amplitude<br>"
                    "- <b>TI field normal to surface (dir_TI_normal):</b> Considers only the component perpendicular to the cortical surface<br>"
                    "- <b>TI field tangential to surface (dir_TI_tangential):</b> Considers only the component parallel to the cortical surface<br><br>"
                    
                    "<b>EEG Net Template:</b><br>"
                    "- Specifies the EEG electrode positions available for optimization<br>"
                    "- Standard templates like EGI_256 provide 256 possible electrode positions<br><br>"
                    
                    "<b>Electrode Parameters:</b><br>"
                    "- <b>Radius:</b> The radius of the electrodes in millimeters<br>"
                    "- <b>Current:</b> The current amplitude in milliamperes (mA)<br>"
                )
            },
            {
                "title": "ROI Definition Methods",
                "content": (
                    "<b>Spherical ROI:</b><br>"
                    "- Define a target region using X, Y, Z coordinates and a radius<br>"
                    "- Coordinates are in subject space (millimeters)<br>"
                    "- Simple way to target a specific location in the brain<br><br>"
                    
                    "<b>Cortical ROI:</b><br>"
                    "- Uses atlas-based parcellation of the cortex<br>"
                    "- Requires selecting an atlas file (.annot) and a label value<br>"
                    "- More anatomically precise way to target specific brain regions<br>"
                    "- Useful when targeting specific functional areas like M1, DLPFC, etc."
                )
            },
            {
                "title": "Optimization Process",
                "content": (
                    "1. The optimization algorithm evaluates many possible electrode positions<br>"
                    "2. For each configuration, it simulates the TI field distribution<br>"
                    "3. The algorithm converges on the set of positions that best achieve the selected goal<br>"
                    "4. Results include optimal electrode positions and simulated field distributions<br><br>"
                    
                    "<b>Note:</b> This is a computationally intensive process and may take several minutes to hours, "
                    "depending on the selected parameters and computational resources."
                )
            },
            {
                "title": "Output and Results",
                "content": (
                    "After optimization completes, results are saved in:<br>"
                    "[PROJECT_DIR]/[SUBJECT_ID]/SimNIBS/flex-search/[ROI_PARAMETERS]/<br><br>"
                    
                    "The results include:<br>"
                    "- Optimal electrode positions for both TI pairs<br>"
                    "- Electric field simulations for the optimal configuration<br>"
                    "- Visualization files compatible with the SimNIBS GUI<br>"
                    "- Log files with optimization parameters and performance metrics"
                )
            },
            {
                "title": "Tips for Effective Optimization",
                "content": (
                    "- Start with the 'Maximize field in target ROI' goal for initial exploration<br>"
                    "- Use spherical ROIs for quick tests, cortical ROIs for precise targeting<br>"
                    "- The 'Maximize focality' goal is useful when targeting areas near sensitive regions<br>"
                    "- Try different EEG net templates if available, as more electrode positions provide more flexibility<br>"
                    "- Standard electrode radius (10mm) and current (2mA) work well for most applications<br>"
                    "- Check the console output for progress and any potential issues"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])
    
    def add_nifti_viewer_help(self, layout):
        """Add NIfTI Viewer help content."""
        # Add header for the NIfTI Viewer tool
        header_label = QtWidgets.QLabel("<h1>NIfTI Viewer Tool</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # NIfTI Viewer sections
        sections = [
            {
                "title": "What are NIfTI Files?",
                "content": (
                    "NIfTI (Neuroimaging Informatics Technology Initiative) files are a standard format "
                    "for storing neuroimaging data. They typically have .nii or .nii.gz extensions and "
                    "contain 3D or 4D volumetric brain data from MRI, fMRI, or simulation results."
                )
            },
            {
                "title": "Interface Overview",
                "content": (
                    "<b>Subject Selection:</b><br>"
                    "- Choose a subject ID from the dropdown<br>"
                    "- Select between Subject space (native) or MNI space (standardized)<br>"
                    "- Click 'Refresh' to update the subject list<br><br>"
                    
                    "<b>Actions:</b><br>"
                    "- <b>Load Subject Data:</b> Loads the selected subject's anatomical (T1) and simulation results<br>"
                    "- <b>Load Custom NIfTI:</b> Opens a file dialog to select your own NIfTI files<br>"
                    "- <b>Reload Current View:</b> Reopens the current files in Freeview<br><br>"
                    
                    "<b>Information Area:</b><br>"
                    "- Displays details about loaded files and settings<br>"
                    "- Shows file paths, sizes, and visualization parameters<br><br>"
                    
                    "<b>Freeview Command:</b><br>"
                    "- Shows the actual command used to launch Freeview<br>"
                    "- Displays visualization parameters for each file"
                )
            },
            {
                "title": "Default Visualization Settings",
                "content": (
                    "When loading subject data, the following default settings are applied:<br><br>"
                    
                    "<b>T1 Anatomical:</b><br>"
                    "- Displayed with grayscale colormap<br>"
                    "- Visible by default<br><br>"
                    
                    "<b>Grey Matter Results:</b><br>"
                    "- 'Heat' colormap showing values between 95-99.9 percentile<br>"
                    "- 70% opacity<br>"
                    "- Visible by default<br><br>"
                    
                    "<b>Full Results:</b><br>"
                    "- 'Heat' colormap showing values between 95-99.9 percentile<br>"
                    "- 70% opacity<br>"
                    "- Hidden by default (must be enabled in Freeview)<br><br>"
                    
                    "<b>Note on Percentile Mode:</b><br>"
                    "The default threshold (95-99.9%) means only the top 5% of values are displayed, "
                    "focusing on the most significant results. This helps identify important areas "
                    "while filtering out noise."
                )
            },
            {
                "title": "Using Freeview Controls",
                "content": (
                    "<b>Basic Navigation:</b><br>"
                    "- Left-click and drag: Rotate 3D view<br>"
                    "- Right-click and drag: Pan<br>"
                    "- Mouse wheel: Zoom in/out<br>"
                    "- Middle-click and drag: Adjust brightness/contrast<br><br>"
                    
                    "<b>Volume Controls:</b><br>"
                    "- Check/uncheck volumes in the left panel to toggle visibility<br>"
                    "- Click volume name to make it the active volume<br>"
                    "- Use sliders to navigate through slices<br>"
                    "- Use toolbar at top for additional view options<br><br>"
                    
                    "<b>Adjusting Display:</b><br>"
                    "- Click on a volume name to select it<br>"
                    "- Right-click on a volume name for additional options<br>"
                    "- Adjust colormap, threshold, and opacity through Freeview's interface<br>"
                    "- Use the 'Configure' button in Freeview for advanced options"
                )
            },
            {
                "title": "Tips for Visualizing Simulation Results",
                "content": (
                    "- View both grey matter and full results for a complete picture<br>"
                    "- Toggle between different overlays to compare results<br>"
                    "- Use the percentile mode for thresholds to focus on significant areas<br>"
                    "- Try different colormaps (heat, jet) for different visualization effects<br>"
                    "- Adjust opacity to see underlying anatomy through the results<br>"
                    "- Save screenshots using Freeview's File > Save Screenshot option"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])
    
    def add_general_usage_tips(self, layout):
        """Add general usage tips."""
        # Add header for general usage tips
        header_label = QtWidgets.QLabel("<h1>General Usage Tips</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # General usage tips section
        sections = [
            {
                "title": "Typical Workflow",
                "content": (
                    "A typical workflow in TI-CSC-2.0 consists of these steps:<br><br>"
                    
                    "1. <b>Pre-processing</b>: Prepare MRI data and create subject-specific head models<br>"
                    "2. <b>Simulation</b>: Run electromagnetic field simulations with selected electrode montages<br>"
                    "3. <b>Optimization </b>: Use Flex Search to find optimal electrode positions<br>"
                    "4. <b>Visualization</b>: View simulation results using the NIfTI Viewer<br><br>"
                    
                    "Each step builds upon the previous one, with output files from earlier stages serving as inputs for later steps."
                )
            },
            {
                "title": "Performance Considerations",
                "content": (
                    "- Pre-processing with FreeSurfer can take several hours per subject<br>"
                    "- Simulations typically take 5-20 minutes depending on complexity<br>"
                    "- Flex Search optimization can take 10 to 30 minutes<br>"
                    "- Using parallel processing can significantly reduce total processing time<br>"
                    "- Consider running long tasks overnight or when the computer is not in use"
                )
            },
            {
                "title": "File Management",
                "content": (
                    "- All data is organized in a subject-centric directory structure<br>"
                    "- Each subject has dedicated directories for raw data, processed files, and results<br>"
                    "- The application automatically creates necessary directories during processing<br>"
                    "- Results are saved in specific subfolders based on the tool and parameters used<br>"
                    "- Avoid manual modification of generated files unless you're sure of what you're doing"
                )
            },
            {
                "title": "Troubleshooting Common Issues",
                "content": (
                    "<b>Missing files or directories:</b><br>"
                    "- Ensure that each subject has the required directory structure<br>"
                    "- Make sure pre-processing steps completed successfully before simulation<br><br>"
                    
                    "<b>Processing errors:</b><br>"
                    "- Check the console output for specific error messages<br>"
                    "- Verify that required external tools (FreeSurfer, SimNIBS) are properly installed<br>"
                    "- In the command line: `freeview` or `simnibs` will inform you about installation success or failure<br><br>"
                    "- Ensure input data (DICOM, NIfTI) is valid and not corrupted<br><br>"
                    
                    "<b>Visualization issues:</b><br>"
                    "- Check that simulation results were generated successfully<br>"
                    "- Try using different visualization parameters if results are not visible"
                )
            },
            {
                "title": "Getting Additional Help",
                "content": (
                    "If you encounter issues not addressed in this help documentation:<br><br>"
                    
                    "- Check the TI-CSC-2.0 GitHub repository for additional documentation<br>"
                    "- Look for known issues or submit new ones on the project's GitHub Issues page<br>"
                    "- Contact the development team for technical support<br>"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"]) 
