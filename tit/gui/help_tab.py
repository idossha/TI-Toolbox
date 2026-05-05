#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Unified help tab for the TI-Toolbox GUI.

Provides scrollable, rich-text documentation covering the BIDS directory
structure, preprocessing, simulation, optimization, analysis, NIfTI
viewing, and system monitoring.
"""

from PyQt5 import QtWidgets, QtCore, QtGui


class HelpTab(QtWidgets.QWidget):
    """Scrollable help centre aggregating documentation for every GUI tool.

    Parameters
    ----------
    parent : QWidget or None
        Parent widget (typically the main window or a floating dialog).
    """

    def __init__(self, parent=None):
        super(HelpTab, self).__init__(parent)
        self.parent = parent
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface for the help tab."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # Introduction text
        intro_label = QtWidgets.QLabel("<h1>TI-Toolbox Help Center</h1>")
        intro_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(intro_label)

        description_label = QtWidgets.QLabel(
            "<p>Welcome to the TI-Toolbox help center. "
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
        self.add_optimizer_help(help_layout)
        self.add_simulator_help(help_layout)
        self.add_analyzer_help(help_layout)
        self.add_nifti_viewer_help(help_layout)
        self.add_system_monitor_help(help_layout)

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
        header_label = QtWidgets.QLabel(
            "<h1>Required Directory Structure (BIDS-compliant)</h1>"
        )
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)

        # Directory structure information
        content = """
        <p>TI-Toolbox follows the BIDS (Brain Imaging Data Structure) conventions for organizing neuroimaging data. This standardized structure ensures compatibility with other neuroimaging tools and facilitates data sharing.</p>
        
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
│   ├── SimNIBS/
│   │   └── sub-{subject}/
│   │       ├── m2m_{subject}/
│   │       ├── Simulations/
│   │       |   └── [montage_name]/
│   │       |       └── Analyses/
│   │       ├── flex-search/
│   │       └── ex-search/
│   └── tit/                         <i>(TI-Toolbox analysis outputs)</i>
│       ├── tissue_analysis/                <i>(tissue analysis results)</i>
│       ├── logs/                           <i>(Log files)</i>
│       └── reports/                        <i>(Report files)</i>
└── code/
    └── tit/                         <i>(Auto-created at first launch)</i>
        └── config/
            ├── montage_list.json
            ├── pre-processing.json
            ├── flex.json
            ├── ex_search.json
            ├── simulator.json
            └── analyzer.json
</pre>

        <h3>Key Points:</h3>
        <ul>
            <li>The <b>sourcedata</b> directory must be set up by the user before preprocessing</li>
            <li>DICOM files must be placed in <code>sourcedata/sub-{subject}/T1w/dicom/</code></li>
            <li>T2w images are optional but can improve head model quality</li>
            <li>All other directories are automatically created during processing</li>
            <li>The <code>code/ti-toolbox</code> directory contains shared configuration files</li>
            <li>TI-Toolbox outputs are organized under <code>derivatives/tit/</code> with subdirectories for tissue analysis, logs, and reports</li>
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
                    "Pre-processing is the first step in preparing neuroimaging data for TI-Toolbox simulations. "
                    "It involves converting DICOM images to NIfTI format, creating head models using FreeSurfer "
                    "and SimNIBS, and preparing the data for subsequent simulation and analysis."
                ),
            },
            {
                "title": "Subject Selection",
                "content": (
                    "<b>Multiple Subject Selection:</b><br>"
                    "- Select one or more subjects from the list using Ctrl+click or Shift+click<br>"
                    "- The 'Refresh List' button updates the subject list from the project directory<br>"
                    "- Use 'Select All' and 'Select None' buttons for quick selection management<br><br>"
                    "Make sure you follow the required BIDS directory structure<br>"
                ),
            },
            {
                "title": "Processing Options",
                "content": (
                    "<b>Convert DICOM files to NIfTI:</b><br>"
                    "- Converts medical DICOM images into NIfTI format (.nii or .nii.gz)<br>"
                    "- Uses <code>sourcedata/sub-{subject}/{T1w,T2w}/dicom/</code> with recursive .dcm/.dicom files or supported archives<br>"
                    "- T1w/T2w are determined by the source folder layout<br><br>"
                    "<b>Create SimNIBS m2m folder:</b><br>"
                    "- Runs the SimNIBS charm tool to create subject-specific head models<br>"
                    "- Generates meshes necessary for electromagnetic field simulations<br>"
                    "- Creates the m2m_{SUBJECT_ID} directory in the SimNIBS folder<br><br>"
                    "<b>Run FreeSurfer recon-all:</b><br>"
                    "- Optional cortical reconstruction using FreeSurfer's recon-all<br>"
                    "- Creates cortical surface models and anatomical parcellations<br>"
                    "- This is a computationally intensive step that can take several hours<br><br>"
                    "<b>Run FreeSurfer reconstruction in parallel:</b><br>"
                    "- Uses Python ThreadPoolExecutor to run recon-all for multiple subjects at once<br>"
                    "- Only applies when 'Run FreeSurfer recon-all' is selected for multiple subjects<br>"
                    "- Each parallel subject runs recon-all with one core; sequential mode lets one subject use FreeSurfer internal parallelism<br><br>"
                    "<b>Run tissue analyzer:</b><br>"
                    "- Analyzes skull bone, skin, and CSF volume and thickness from segmented tissue data<br>"
                    "- Results are saved in <code>derivatives/ti-toolbox/tissue_analysis/sub-{subject}/</code><br>"
                ),
            },
            {
                "title": "Processing Workflow",
                "content": (
                    "The typical pre-processing workflow follows these steps:<br><br>"
                    "1. <b>DICOM to NIfTI Conversion:</b><br>"
                    "   - Raw DICOM files are identified and converted to NIfTI format<br>"
                    "   - T1 and T2 images are detected and properly named<br><br>"
                    "2. <b>SimNIBS Head Model Creation:</b><br>"
                    "   - Uses the SimNIBS charm tool to create realistic head models<br>"
                    "   - Generates mesh files for FEM simulations and subject atlas annotations<br><br>"
                    "3. <b>FreeSurfer Reconstruction (Optional):</b><br>"
                    "   - T1 images and optionally T2 images are processed using FreeSurfer's recon-all<br>"
                    "   - Creates cortical surface models and segmentation of brain structures<br>"
                    "   - Can be run in parallel for multiple subjects<br><br>"
                    "4. <b>Tissue Analysis (Optional):</b><br>"
                    "   - Analyzes skull, skin, and CSF volume and thickness from segmented tissue data<br>"
                    "   - Results saved in <code>derivatives/ti-toolbox/tissue_analysis/sub-{subject}/</code><br><br>"
                    "Once pre-processing is complete, the subject data is ready for TI-Toolbox simulations."
                ),
            },
            {
                "title": "Tips and Troubleshooting",
                "content": (
                    "- Ensure that raw DICOM files are organized under <code>sourcedata/sub-{subject}/{T1w,T2w}/dicom/</code><br>"
                    "- T1-weighted MRI scans are required for SimNIBS; recon-all is optional unless your analysis needs FreeSurfer outputs<br>"
                    "- T2-weighted MRI scans are optional but improve head model quality<br>"
                    "- When processing multiple subjects with recon-all, consider parallel processing for throughput<br>"
                    "- The Console Output window shows real-time progress and any error messages<br>"
                    "- Detailed log files are saved under <code>derivatives/ti-toolbox/logs/sub-{subject}/</code><br>"
                    "- If processing fails, check the console output and per-subject log files for specific error messages<br>"
                    "- The Stop button can be used to terminate processing, but may leave files in an inconsistent state<br>"
                    "- Use the status label at the top to monitor the current processing state<br>"
                    "- The tissue analyzer requires completed SimNIBS processing<br>"
                    "- Tissue analysis results are automatically organized under the tit derivative structure"
                ),
            },
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
                "title": "What is the TI-Toolbox Simulator?",
                "content": (
                    "The TI-Toolbox Simulator performs computational simulations of Temporal Interference (TI) stimulation "
                    "using finite element modeling (FEM). It calculates electric field distributions in subject-specific "
                    "head models for different electrode configurations and stimulation parameters."
                    "It uses SimNIBS' TI module to simulate the electric field distribution based on Grossman's equation from the 2017 paper."
                ),
            },
            {
                "title": "Subject Selection",
                "content": (
                    "- Select one or more subjects from the list using Ctrl+click or Shift+click<br>"
                    "- Each subject must have been pre-processed with a SimNIBS head model<br>"
                    "- The subject list automatically populates with available subjects<br>"
                    "- Use the 'Refresh List' button to update the subject list"
                ),
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
                    "- For Unipolar mode, specify two pairs of electrode positions<br>"
                    "- For Multipolar mode, specify four pairs of electrode positions<br>"
                    "- Position names should match the desired EEG net"
                ),
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
                ),
            },
            {
                "title": "Simulation Process",
                "content": (
                    "1. The simulator creates FEM models for each electrode configuration<br>"
                    "2. It solves the electric field equations using SimNIBS<br>"
                    "3. For TI stimulation, it calculates the maximal amplitude-modulated field<br>"
                    "4. Results are stored in the subject's SimNIBS directory<br><br>"
                    "Simulation progress and status messages are displayed in the console window."
                ),
            },
            {
                "title": "Output Files",
                "content": (
                    "Simulation results are saved in:<br>"
                    "<code>derivatives/SimNIBS/sub-{subject}/Simulations/{montage_name}/</code><br><br>"
                    "Output includes:<br>"
                    "- Electric field distributions (.msh and .nii.gz formats)<br>"
                    "- Electrode positions and parameters<br>"
                    "- Log files with simulation parameters<br>"
                    "- Visualization-ready files compatible with Gmsh and NIfTI viewers"
                ),
            },
        ]

        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])

    def add_optimizer_help(self, layout):
        """Add Optimizer help content (Flex-Search and Ex-Search)."""
        # Add header for the Optimizer tool
        header_label = QtWidgets.QLabel("<h1>Optimizer Tool</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)

        # Optimizer overview
        self.add_section(
            layout,
            "Overview",
            (
                "The Optimizer tab combines two electrode optimization methods under a single interface. "
                "Use the dropdown at the top of the tab to switch between:<br><br>"
                "- <b>Flex-Search</b> (Weise et al. 2025): Differential evolution / genetic algorithm optimization<br>"
                "- <b>Ex-Search</b>: Exhaustive (brute-force) search using leadfield matrices<br><br>"
                "Both methods find electrode montages that maximize the electric field in a target brain region. "
                "Flex-Search is faster and explores a wider solution space, while Ex-Search guarantees a global optimum "
                "within the selected EEG net at the cost of longer computation time."
            ),
        )

        # Flex-Search sections
        flex_sections = [
            {
                "title": "Flex-Search: What Is It?",
                "content": (
                    "Flex-Search uses a differential evolution algorithm to find electrode montages that maximize the electric field "
                    "in a target brain region while minimizing stimulation to non-target areas. It efficiently explores "
                    "the solution space without needing to precompute leadfield matrices."
                ),
            },
            {
                "title": "Flex-Search: Optimization Parameters",
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
                    "- Select the EEG net to constrain electrode placement<br>"
                ),
            },
            {
                "title": "Flex-Search: Target Region Selection",
                "content": (
                    "<b>Region of Interest (ROI):</b><br>"
                    "- Select a target brain region from the predefined atlas list<br>"
                    "- ROIs are defined according to various atlases (Desikan-Killiany, Destrieux, etc.)<br>"
                    "- Create a custom ROI by specifying a spherical target in RAS coordinates in subject space<br>"
                    "- The sphere is defined by a center point (x,y,z) and radius in millimeters<br>"
                    "- Coordinates must be in the subject's native space (not MNI space)<br><br>"
                    "<b>Non-ROI Regions (for focality optimization):</b><br>"
                    "- Specify regions to avoid stimulating<br>"
                    "- Can be selected from the same atlas as the target ROI<br>"
                    "- Helps in achieving more focal stimulation"
                ),
            },
            {
                "title": "Flex-Search: Search Process",
                "content": (
                    "1. Creates an initial population of random electrode configurations<br>"
                    "2. Evaluates each solution by running a simplified simulation<br>"
                    "3. The best solutions are selected for the next generation<br>"
                    "4. New solutions are created through crossover and mutation<br>"
                    "5. The process repeats until convergence or the maximum number of generations<br>"
                    "6. The best solutions are presented in ranked order<br><br>"
                    "Results are saved in the subject's flex-search directory and can be visualized in the NIfTI Viewer."
                ),
            },
        ]

        for section in flex_sections:
            self.add_section(layout, section["title"], section["content"])

        # Ex-Search sections
        ex_sections = [
            {
                "title": "Ex-Search: What Is It?",
                "content": (
                    "Ex-Search systematically evaluates all electrode combinations within a specified EEG net "
                    "using precomputed leadfield matrices. This guarantees finding the globally optimal montage "
                    "for the selected net at the cost of longer computation time."
                ),
            },
            {
                "title": "Ex-Search: Leadfield Generation",
                "content": (
                    "<b>Leadfield Files:</b><br>"
                    "- Required before running Ex-Search<br>"
                    "- Generated using SimNIBS for each subject and EEG net combination<br>"
                    "- Specific to both subject and EEG net<br><br>"
                    "<b>Important Considerations:</b><br>"
                    "- Higher electrode density results in larger leadfield files and longer generation time<br>"
                    "- Process may take several minutes to hours depending on the net size<br>"
                    "- Ensure sufficient disk space for leadfield storage<br><br>"
                    "<b>Creating Leadfields:</b><br>"
                    "- Click 'Create Leadfield' to generate leadfield files<br>"
                    "- Progress is shown in the console window"
                ),
            },
            {
                "title": "Ex-Search: ROI Selection",
                "content": (
                    "<b>Adding ROIs:</b><br>"
                    "- Click 'Add ROI' to create a new target region<br>"
                    "- ROIs can be defined using atlas regions or spherical targets<br>"
                    "- Multiple ROIs can be added for batch processing<br><br>"
                    "<b>Managing ROIs:</b><br>"
                    "- Select ROIs from the list to remove them<br>"
                    "- Each ROI will be processed for the selected subject"
                ),
            },
            {
                "title": "Ex-Search: Search Process",
                "content": (
                    "1. For each pair of electrodes (E1+, E1- and E2+, E2-), all possible combinations are generated "
                    "using the Cartesian product of electrode positions<br>"
                    "2. For each combination, the electric field distribution is calculated from the leadfield<br>"
                    "3. The field is evaluated in the target ROI(s)<br>"
                    "4. Results are ranked by field strength in the target region<br><br>"
                    "Results are saved in the subject's ex-search directory with CSV files containing "
                    "electrode configurations and scores for each ROI."
                ),
            },
        ]

        for section in ex_sections:
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
                    "The Analyzer tool provides comprehensive analysis and visualization capabilities for TI-Toolbox simulation results. "
                    "It allows you to compare different electrode configurations, analyze electric field distributions, "
                    "and generate reports for your stimulation studies."
                ),
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
                ),
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
                ),
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
                ),
            },
            {
                "title": "Results Management",
                "content": (
                    "<b>Data Organization:</b><br>"
                    "- Results are organized by subject and simulation<br>"
                    "- Analysis results are saved under <code>derivatives/SimNIBS/sub-{subject}/Simulations/{montage}/Analyses/</code><br>"
                    "- Previous analyses can be loaded and modified<br><br>"
                    "<b>Report Generation:</b><br>"
                    "- Generates HTML reports with interactive visualizations<br>"
                    "- Reports include slice series, montage diagrams, field statistics, and ROI summaries<br>"
                    "- Reports are saved in <code>derivatives/tit/reports/</code>"
                ),
            },
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
                ),
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
                ),
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
                ),
            },
        ]

        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])

    def add_system_monitor_help(self, layout):
        """Add System Monitor help content."""
        # Add header for the System Monitor tool
        header_label = QtWidgets.QLabel("<h1>System Monitor</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)

        sections = [
            {
                "title": "What is the System Monitor?",
                "content": (
                    "The System Monitor provides real-time monitoring of system resources and toolbox-related processes. "
                    "It helps you track CPU usage, memory consumption, and the status of running operations such as "
                    "FreeSurfer reconstruction, SimNIBS simulations, and optimization searches."
                ),
            },
            {
                "title": "Monitored Processes",
                "content": (
                    "The monitor automatically detects and displays processes related to:<br>"
                    "- <b>SimNIBS</b>: charm, simnibs simulations<br>"
                    "- <b>FreeSurfer</b>: recon-all, surface reconstruction<br>"
                    "- <b>Pre-processing</b>: dcm2niix, FSL tools (bet, fast, flirt, fnirt)<br>"
                    "- <b>TI-Toolbox</b>: optimization, analysis, and simulation scripts<br><br>"
                    "System-wide CPU and memory usage graphs are updated in real time."
                ),
            },
            {
                "title": "Tips",
                "content": (
                    "- Use the System Monitor to check if a long-running process is still active<br>"
                    "- Monitor memory usage when processing multiple subjects simultaneously<br>"
                    "- The process list updates automatically every few seconds"
                ),
            },
        ]

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
                    "1. Begin with the <b>Pre-processing</b> tab to prepare your data<br>"
                    "2. Use the <b>Optimizer</b> tab to find optimal electrode placements (Flex-Search or Ex-Search)<br>"
                    "3. Use the <b>Simulator</b> tab when you want full control over stimulation parameters<br>"
                    "4. Use the <b>Analyzer</b> tab to explore simulation results and generate reports<br>"
                    "5. Visualize results with the <b>NIfTI Viewer</b> tab<br>"
                    "6. Monitor running processes with the <b>System Monitor</b> tab<br><br>"
                    "The workflow is designed to be sequential, but you can jump to any step if your data is already prepared. "
                    "Help, Contact, and Acknowledgments are accessible via the settings gear icon in the top-right corner."
                ),
            },
            {
                "title": "Performance Tips",
                "content": (
                    "- Pre-processing is computationally intensive, especially FreeSurfer reconstruction<br>"
                    "- Consider using parallel processing for multiple subjects<br>"
                    "- Close unused applications to free up memory<br>"
                    "- For large datasets, consider processing overnight or on a strong compute server"
                ),
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
                    "- Ensure X11 / XQuartz is installed and configured on your system<br>"
                ),
            },
            {
                "title": "Data Management",
                "content": (
                    "- Regularly back up your project directory<br>"
                    "- Simulation results can take up significant disk space<br>"
                    "- Ex-Search results take up significant disk space and should be cleaned regularly<br>"
                    "- Use meaningful subject IDs and montage names for easy identification<br>"
                    "- Keep notes about processing parameters and decisions"
                ),
            },
        ]

        # Add each section to the help layout
        for section in sections:
            self.add_section(layout, section["title"], section["content"])
