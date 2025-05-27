#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Help Tab for TI-CSC GUI
This module provides a unified help tab for all TI-CSC tools.
"""

from PyQt5 import QtWidgets, QtCore, QtGui

class HelpTab(QtWidgets.QWidget):
    """Unified help tab for TI-CSC  GUI."""
    
    def __init__(self, parent=None):
        super(HelpTab, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface for the help tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Introduction text
        intro_label = QtWidgets.QLabel("<h1>TI-CSC Help Center</h1>")
        intro_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(intro_label)
        
        description_label = QtWidgets.QLabel(
            "<p>Welcome to the TI-CSC help center. "
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
        
        # Add directory structure first (most important for new users)
        self.add_directory_structure(help_layout)
        
        # Add sections from all tools
        self.add_pre_processing_help(help_layout)
        self.add_simulator_help(help_layout)
        self.add_flex_search_help(help_layout)
        self.add_ex_search_help(help_layout)
        self.add_analyzer_help(help_layout)
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
    
    def add_directory_structure(self, layout):
        """Add directory structure information."""
        # Add header
        header_label = QtWidgets.QLabel("<h1>Required Directory Structure (BIDS-compliant)</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Directory structure information
        content = """
        <p>TI-CSC follows the BIDS (Brain Imaging Data Structure) conventions for organizing neuroimaging data. This standardized structure ensures compatibility with other neuroimaging tools and facilitates data sharing.</p>
        
        <p><b>Important:</b> Users need to set up the sourcedata directory with their DICOM files. Most other directories are automatically created during processing.</p>
        
        <h3>Directory Structure:</h3>
        <pre style='background-color: #f5f5f5; padding: 10px; border-radius: 5px; font-family: monospace;'>
Project Directory/
├── sub-{subject}/                           <i>(Auto-created during preprocessing)</i>
│   ├── anat/
│   │   ├── sub-{subject}_space-XXX_T1w.nii.gz
│   │   ├── sub-{subject}_space-XXX_T1w.json
│   │   ├── sub-{subject}_space-XXX_T2w.nii.gz
│   │   └── sub-{subject}_space-XXX_T2w.json
│   ├── dwi/                                <i>(Optional: For diffusion data)</i>
│   ├── eeg/                                <i>(Optional: For EEG data)</i>
│   ├── func/                               <i>(Optional: For functional MRI data)</i>
│   └── beh/                                <i>(Optional: For behavioral data)</i>
├── sourcedata/                             <i>(Required: Set up by user)</i>
│   └── sub-{subject}/
│       ├── T1w/
│       │   └── dicom/                      <i>(Place T1w DICOM files here)</i>
│       ├── T2w/                            <i>(Optional)</i>
│       │   └── dicom/                      <i>(Place T2w DICOM files here)</i>
│       └── additional_files/               <i>(Optional documentation)</i>
├── derivatives/                            <i>(Auto-created during pre-processing)</i>
│   ├── freesurfer/                         
│   │   └── sub-{subject}/
│   │       ├── mri/
│   │       └── label/
│   └── SimNIBS/
│       └── sub-{subject}/
│           ├── m2m_{subject}/
│           ├── Simulations/
│           ├── flex-search/
│           └── ex-search/
└── ti-csc/                                 <i>(Auto-created at first launch)</i>
    └── config/
        ├── montage_list.json
        ├── flex-search_config/
        ├── ex-search_config/
        ├── simulator_config/
        └── entrypoint_config/
</pre>

        <h3>Key Points:</h3>
        <ul>
            <li>The <b>sourcedata</b> directory must be set up by the user before preprocessing</li>
            <li>DICOM files must be placed in <code>sourcedata/sub-{subject}/T1w/dicom/</code></li>
            <li>T2w images are optional but can improve head model quality</li>
            <li>All other directories are automatically created during processing</li>
            <li>The <code>ti-csc</code> directory contains shared configuration files</li>
        </ul>
        
        <h3>Getting Started:</h3>
        <ol>
            <li>Create your project directory (e.g., "my_project")</li>
            <li>Create the sourcedata directory structure</li>
            <li>Create a subject folder in sourcedata (e.g., "sub-101")</li>
            <li>Place T1w DICOM files in <code>sourcedata/sub-101/T1w/dicom/</code></li>
            <li>Optionally add T2w DICOM files in <code>sourcedata/sub-101/T2w/dicom/</code></li>
            <li>Use the Pre-processing tab to begin processing</li>
        </ol>

        <h3>Example Subject IDs:</h3>
        <p>Subject IDs should follow the BIDS naming convention:</p>
        <ul>
            <li>Single subject: sub-101</li>
            <li>Multiple subjects: sub-101, sub-102, etc.</li>
        </ul>
        """
        
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
                    "- The 'Refresh List' button updates the subject list from the project directory<br>"
                    "- Use 'Select All' and 'Select None' buttons for quick selection management<br><br>"
                    
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
                    "   - Creates cortical surface models and segmentation of brain structures<br>"
                    "   - Can be run in parallel for multiple subjects<br><br>"
                    
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
                    "- T1-weighted MRI scans are required for SimNIBS & FreeSurfer reconstruction<br>"
                    "- T2-weighted MRI scans are optional but improve head model quality<br>"
                    "- When processing multiple subjects, consider using parallel processing<br>"
                    "- The Console Output window shows real-time progress and any error messages<br>"
                    "- If processing fails, check the console output for specific error messages<br>"
                    "- The Stop button can be used to terminate processing, but may leave files in an inconsistent state<br>"
                    "- Use the status label at the top to monitor the current processing state"
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
                    "It uses SimNIBS' TI module to simulate the electric field distribution based on Grossman's equation from the 2017 paper."
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
                    "- The montage list is populated based on the selected simulation mode and EEG net<br>"
                    "- Multiple montages can be selected for batch processing<br><br>"
                    
                    "<b>Custom Montage:</b><br>"
                    "- Use the 'Add Custom Montage' button to create new electrode configurations<br>"
                    "- For Multipolar mode, specify four pairs of electrode positions<br>"
                    "- For Unipolar mode, specify two pairs of electrode positions<br>"
                    "- Position names should match the desired EEG net"
                )
            },
            {
                "title": "Simulation Parameters",
                "content": (
                    "<b>Simulation Type:</b><br>"
                    "- <b>Standard isotropic:</b> Uses default conductivity values for all tissue types<br>"
                    "- <b>Anisotropic:</b> Takes into account the anisotropy of the tissue based on a DTI scan<br><br>"
                    
                    "<b>Simulation Mode:</b><br>"
                    "- <b>Unipolar:</b> Uses two pairs for conventional TI stimulation<br>"
                    "- <b>Multipolar:</b> Uses four pairs of electrodes for mTI stimulation<br><br>"
                    
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
        """Add Flex-Search help content."""
        # Add header for the Flex-Search tool
        header_label = QtWidgets.QLabel("<h1>Flex-Search Tool</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Flex-Search sections
        sections = [
            {
                "title": "What is Flex-Search?",
                "content": (
                    "Flex-Search is an optimization algorithm for finding electrode montages that maximize the electric field strength "
                    "in a target brain region while minimizing stimulation to non-target regions. It uses a genetic algorithm to "
                    "explore different electrode configurations and find optimal or near-optimal solutions."
                )
            },
            {
                "title": "Subject Selection",
                "content": (
                    "- Select a subject from the list who has already been pre-processed<br>"
                    "- The subject must have a complete SimNIBS head model<br>"
                    "- Only one subject can be selected for each Flex-Search run<br>"
                    "- Use the 'Refresh' button to update the subject list"
                )
            },
            {
                "title": "Optimization Parameters",
                "content": (
                    "<b>Optimization Goal:</b><br>"
                    "- <b>mean:</b> Maximize mean field in target ROI<br>"
                    "- <b>max:</b> Maximize peak field in target ROI<br>"
                    "- <b>focality:</b> Maximize field in target ROI while minimizing field elsewhere<br><br>"
                    
                    "<b>Post-processing Method:</b><br>"
                    "- <b>max_TI:</b> Maximum TI field<br>"
                    "- <b>dir_TI_normal:</b> TI field normal to surface<br>"
                    "- <b>dir_TI_tangential:</b> TI field tangential to surface<br><br>"
                    
                    "<b>Electrode Parameters:</b><br>"
                    "- <b>Radius:</b> Electrode size in millimeters (1-30mm)<br>"
                    "- <b>Current:</b> Stimulation intensity in milliamperes (0.1-5mA)<br><br>"
                    
                    "<b>EEG Net Template:</b><br>"
                    "- Select the EEG net to map nearest electrodes<br>"
                )
            },
            {
                "title": "Target Region Selection",
                "content": (
                    "<b>Region of Interest (ROI):</b><br>"
                    "- Select a target brain region from the predefined list<br>"
                    "- The ROI list is populated based on available parcellations<br>"
                    "- ROIs are defined according to various atlases (Desikan-Killiany, Destrieux, etc.)<br><br>"
                    
                    "- Create a custom ROI by specifying a spherical target in RAS coordinates in subject space<br>"
                    "- The sphere is defined by a center point (x,y,z) and radius in millimeters<br>"
                    "- Coordinates must be in the subject's native space (not MNI space)<br><br>"
                    
                    "<b>Non-ROI Regions (for focality optimization):</b><br>"
                    "- Specify regions to avoid stimulating<br>"
                    "- Can be selected from the same atlas as the target ROI<br>"
                    "- Helps in achieving more focal stimulation"
                )
            },
            {
                "title": "Search Process",
                "content": (
                    "1. Flex-Search creates an initial population of random electrode configurations<br>"
                    "2. It evaluates each solution by running a simplified simulation<br>"
                    "3. The best solutions are selected for the next generation<br>"
                    "4. New solutions are created through crossover and mutation<br>"
                    "5. The process repeats until convergence or the maximum number of generations<br>"
                    "6. The best solutions are presented in ranked order<br><br>"
                    
                    "The search progress and status are displayed in the console window."
                )
            },
            {
                "title": "Results and Visualization",
                "content": (
                    "- The top solutions are displayed in a ranked list<br>"
                    "- Each solution shows electrode positions and fitness scores<br>"
                    "- Solutions can be exported for use in the Simulator<br>"
                    "- Results can be visualized using the NIfTI Viewer<br>"
                    "- Detailed results are saved in the subject's flex-search directory"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])
    
    def add_ex_search_help(self, layout):
        """Add Ex-Search help content."""
        # Add header for the Ex-Search tool
        header_label = QtWidgets.QLabel("<h1>Ex-Search Tool</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Ex-Search sections
        sections = [
            {
                "title": "What is Ex-Search?",
                "content": (
                    "Ex-Search is an exhaustive search tool for finding optimal electrode configurations for temporal interference "
                    "stimulation. It systematically evaluates electrode combinations within a specified EEG net to find "
                    "the best montages for targeting specific brain regions. The search process is optimized to efficiently "
                    "explore the solution space while maintaining accuracy."
                )
            },
            {
                "title": "Subject Selection",
                "content": (
                    "- Select a single subject from the list<br>"
                    "- The subject must have completed pre-processing and have leadfield files<br>"
                    "- Only one subject can be processed at a time<br>"
                    "- The 'Refresh List' button updates the subject list"
                )
            },
            {
                "title": "Leadfield Generation",
                "content": (
                    "<b>Leadfield Files:</b><br>"
                    "- Required for Ex-Search optimization<br>"
                    "- Generated using SimNIBS for each subject and EEG net combination<br>"
                    "- Must be created before running the search<br><br>"
                    
                    "<b>Important Considerations:</b><br>"
                    "- Leadfields are specific to both subject and EEG net<br>"
                    "- Higher electrode density in the net results in larger leadfield files<br>"
                    "- Generation time increases with electrode density<br>"
                    "- Process may take several minutes to hours depending on the net size<br><br>"
                    
                    "<b>Creating Leadfields:</b><br>"
                    "- Click 'Create Leadfield' to generate leadfield files<br>"
                    "- Progress is shown in the console window<br>"
                    "- Ensure sufficient disk space for leadfield storage"
                )
            },
            {
                "title": "ROI Selection",
                "content": (
                    "<b>Adding ROIs:</b><br>"
                    "- Click 'Add ROI' to create a new target region<br>"
                    "- ROIs can be defined using atlas regions or spherical targets<br>"
                    "- Multiple ROIs can be added for batch processing<br><br>"
                    
                    "<b>Managing ROIs:</b><br>"
                    "- Select ROIs from the list to remove them<br>"
                    "- ROIs can be edited by removing and re-adding them<br>"
                    "- Each ROI will be processed for the selected subject"
                )
            },
            {
                "title": "Search Process",
                "content": (
                    "1. Ex-Search uses a systematic approach to generate electrode combinations:<br>"
                    "   - For each pair of electrodes (E1+, E1- and E2+, E2-), all possible combinations are generated<br>"
                    "   - The process uses the Cartesian product of the electrode lists<br>"
                    "   - This ensures comprehensive coverage of possible montages while minimizing comupte time.<br><br>"
                    
                    "2. The search process follows these steps:<br>"
                    "   - First, all valid combinations of E1+ and E1- electrodes are generated<br>"
                    "   - Then, all valid combinations of E2+ and E2- electrodes are generated<br>"
                    "   - Finally, these pairs are combined to create complete montages<br><br>"
                    
                    "3. For each combination:<br>"
                    "   - The electric field distribution is calculated<br>"
                    "   - The field is evaluated in the target ROI(s)<br>"          
                    
                    "The search progress and status are displayed in the console window."
                )
            },
            {
                "title": "Results and Analysis",
                "content": (
                    "- Results are saved in the subject's ex-search directory<br>"
                    "- Each ROI gets its own results folder<br>"
                    "- Results include CSV files with electrode configurations and scores<br>"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])
    
    def add_analyzer_help(self, layout):
        """Add Analyzer help content."""
        # Add header for the Analyzer tool
        header_label = QtWidgets.QLabel("<h1>Analyzer Tool</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Analyzer sections
        sections = [
            {
                "title": "What is the Analyzer?",
                "content": (
                    "The Analyzer tool provides comprehensive analysis and visualization capabilities for TI-CSC simulation results. "
                    "It allows you to compare different electrode configurations, analyze electric field distributions, "
                    "and generate reports for your stimulation studies."
                )
            },
            {
                "title": "Data Selection",
                "content": (
                    "<b>Subject Selection:</b><br>"
                    "- Select one or more subjects from the list<br>"
                    "- Subjects must have completed simulations<br>"
                    "- Use 'Select All' and 'Clear' buttons for quick selection<br><br>"
                    
                    "<b>Simulation Selection:</b><br>"
                    "- Choose from available simulations for each subject<br>"
                    "- Multiple simulations can be selected for comparison<br>"
                    "- Results from Flex-Search and Ex-Search can also be analyzed"
                )
            },
            {
                "title": "Analysis Options",
                "content": (
                    "<b>Field Analysis:</b><br>"
                    "- Calculate mean, maximum, and minimum field strengths<br>"
                    "- Analyze field focality and penetration depth<br>"
                    "- Compare field distributions across different montages<br><br>"
                    
                    "<b>ROI Analysis:</b><br>"
                    "- Evaluate field strength in specific brain regions<br>"
                    "- Compare stimulation effects across ROIs<br>"
                    "- Generate ROI-specific statistics<br><br>"
                    
                    "<b>Comparative Analysis:</b><br>"
                    "- Compare results across different subjects<br>"
                    "- Analyze effects of different electrode configurations<br>"
                    "- Generate comparative reports and visualizations"
                )
            },
            {
                "title": "Visualization Tools",
                "content": (
                    "<b>Field Maps:</b><br>"
                    "- View electric field distributions in 3D<br>"
                    "- Overlay fields on anatomical images<br>"
                    "- Adjust visualization parameters in real-time<br><br>"
                    
                    "<b>Statistical Plots:</b><br>"
                    "- Generate histograms of field distributions<br>"
                    "- Create box plots for comparing montages<br>"
                    "- Plot field strength vs. depth profiles<br><br>"
                    
                    "<b>Export Options:</b><br>"
                    "- Save visualizations as high-resolution images<br>"
                    "- Export data for further analysis<br>"
                    "- Generate comprehensive PDF reports"
                )
            },
            {
                "title": "Results Management",
                "content": (
                    "<b>Data Organization:</b><br>"
                    "- Results are organized by subject and simulation<br>"
                    "- Analysis results are saved in the subject's analysis directory<br>"
                    "- Previous analyses can be loaded and modified<br><br>"
                    
                    "<b>Report Generation:</b><br>"
                    "- Create detailed reports of analysis results<br>"
                    "- Include visualizations and statistics<br>"
                    "- Export reports in various formats (PDF, HTML, etc.)"
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
                "title": "What is the NIfTI Viewer?",
                "content": (
                    "The NIfTI Viewer is a built-in visualization tool for exploring 3D neuroimaging data in NIfTI format. "
                    "It allows you to view anatomical images, simulation results, and overlays to assess the spatial "
                    "distribution of electric fields and stimulation effects."
                )
            },
            {
                "title": "Loading Data",
                "content": (
                    "<b>Automatic Loading:</b><br>"
                    "- When you select a subject and simulation, results are automatically loaded<br>"
                    "- The viewer shows anatomical images with electric field overlays<br><br>"
                    
                    "<b>Manual Loading:</b><br>"
                    "- Use the 'Load NIfTI' button to open any NIfTI (.nii or .nii.gz) file<br>"
                    "- Multiple files can be loaded and overlaid<br>"
                    "- The file browser starts in the subject's directory for easy navigation"
                )
            },
            {
                "title": "Tips and Shortcuts",
                "content": (
                    "- <b>Mouse Wheel:</b> Scroll through slices<br>"
                    "- <b>Right-Click + Drag:</b> Adjust brightness/contrast<br>"
                    "- <b>Middle-Click + Drag:</b> Pan the view<br>"
                    "- <b>Ctrl + Wheel:</b> Zoom in/out<br>"
                    "- <b>Spacebar:</b> Reset view to default<br>"
                    "- <b>L:</b> Toggle crosshair visibility<br>"
                    "- <b>S:</b> Synchronize views when multiple datasets are loaded<br>"
                    "- <b>1-9:</b> Quick navigation to percentile positions"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])
    
    def add_general_usage_tips(self, layout):
        """Add general usage tips."""
        # Add header for general tips
        header_label = QtWidgets.QLabel("<h1>General Usage Tips</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # General tips sections
        sections = [
            {
                "title": "Getting Started",
                "content": (
                    "1. Begin with the Pre-processing tab to prepare your data<br>"
                    "2. Explore optimization with the Flex-Search or Ex-Search tab<br>"
                    "3. Use the Simulator tab when you want maximum control over the stimulation parameters<br>"
                    "4. Use the Analyzer tab to explore the results of the simulations<br>"
                    "5. Visualize results with the NIfTI Viewer tab<br><br>"
                
                    "The workflow is designed to be sequential, but you can jump to any step if your data is already prepared."
                )
            },
            {
                "title": "Performance Tips",
                "content": (
                    "- Pre-processing is computationally intensive, especially FreeSurfer reconstruction<br>"
                    "- Consider using parallel processing for multiple subjects<br>"
                    "- Close unused applications to free up memory<br>"
                    "- For large datasets, consider processing overnight or on a strong compute server"
                )
            },
            {
                "title": "Common Issues",
                "content": (
                    "<b>File Not Found Errors:</b><br>"
                    "- Ensure your data follows the required directory structure<br>"
                    "- Check file permissions and ownership<br>"
                    "- Verify that all prerequisite steps have been completed<br><br>"
                    
                    "<b>Processing Failures:</b><br>"
                    "- Check the console output for specific error messages<br>"
                    "- Verify that input data (e.g., DICOM files) is valid and complete<br><br>"
                    
                    "<b>Visualization Issues:</b><br>"
                    "- Ensure X11 / XQuartz is installed and configuredon your system<br>"
                )
            },
            {
                "title": "Data Management",
                "content": (
                    "- Regularly back up your project directory<br>"
                    "- Simulation results can take up significant disk space<br>"
                    "- Ex-search results take up significatn disk space and should be cleaned regularly<br>"
                    "- Use meaningful subject IDs and montage names for easy identification<br>"
                    "- Keep notes about processing parameters and decisions"
                )
            }
        ]
        
        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"]) 
