"""
TI-Toolbox Version Information
Contains version, tool, and system information for the TI-Toolbox application.
"""

__version__ = "2.2.1"

# TI-Toolbox Core Information
TI_CSC_INFO = {
    "version": "2.2.1",
    "release_date": "December 04, 2025", 
    "build": "stable"
}

# Docker Images Information
DOCKER_IMAGES = {
    "core": {
        "version": "2.2.1",
        "tag": "idossha/simnibs:v2.2.1",
        "description": "Core SimNIBS image with TI tools",
        "size": "~8GB"
    },
    "freesurfer": {
        "version": "2.2.1",
        "tag": "freesurfer/freesurfer:7.4.1",
        "description": "FreeSurfer - Brain Analysis and Segmentation",
        "size": "~9GB"
    },
    "fsl": {
        "version": "2.2.1", 
        "tag": "brainlife/fsl:6.0.7.4",
        "description": "FSL - FMRIB Software Library",
        "size": "~4GB"
    }
}

# Neuroimaging Tools Information
TOOLS_INFO = {
    "freesurfer": {
        "version": "2.2.1",
        "description": "Cortical reconstruction and brain segmentation",
        "website": "https://surfer.nmr.mgh.harvard.edu/",
        "license": "FreeSurfer License"
    },
    "simnibs": {
        "version": "2.2.1", 
        "description": "Finite element method for brain stimulation",
        "website": "https://simnibs.github.io/simnibs/",
        "license": "GPL v3"
    },
    "fsl": {
        "version": "2.2.1",
        "description": "Comprehensive library of analysis tools for FMRI, MRI and DTI",
        "website": "https://fsl.fmrib.ox.ac.uk/",
        "license": "FSL License"
    },
    "dcm2niix": {
        "version": "2.2.1",
        "description": "DICOM to NIfTI converter",
        "website": "https://github.com/rordenlab/dcm2niix",
        "license": "BSD 2-Clause"
    },
    "nibabel": {
        "version": "2.2.1",
        "description": "Python library for neuroimaging data I/O",
        "website": "https://nipy.org/nibabel/",
        "license": "MIT"
    },
    "numpy": {
        "version": "2.2.1",
        "description": "Numerical computing library",
        "website": "https://numpy.org/",
        "license": "BSD"
    },
    "scipy": {
        "version": "2.2.1",
        "description": "Scientific computing library", 
        "website": "https://scipy.org/",
        "license": "BSD"
    },
    "matplotlib": {
        "version": "2.2.1",
        "description": "Plotting and visualization library",
        "website": "https://matplotlib.org/",
        "license": "PSF"
    },
    "pandas": {
        "version": "2.2.1",
        "description": "Data analysis and manipulation library",
        "website": "https://pandas.pydata.org/",
        "license": "BSD"
    },
    "vtk": {
        "version": "2.2.1",
        "description": "3D graphics and visualization toolkit",
        "website": "https://vtk.org/",
        "license": "BSD"
    },
    "gmsh": {
        "version": "2.2.1",
        "description": "3D finite element mesh generator",
        "website": "https://gmsh.info/",
        "license": "GPL"
    }
}

# System Requirements
SYSTEM_REQUIREMENTS = {
    "min_ram": "32GB",
    "recommended_ram": "64GB+",
    "disk_space": "~30GB for all images",
    "docker_version": "4.0+",
    "supported_os": [
        "macOS 10.14+",
        "Windows 10+", 
        "Ubuntu 18.04+",
        "CentOS 7+"
    ]
}

# TI-Toolbox Capabilities  
CAPABILITIES = {
    "preprocessing": [
        "DICOM to NIfTI conversion",
        "FreeSurfer cortical reconstruction", 
        "SimNIBS head modeling",
        "BIDS dataset organization"
    ],
    "simulation": [
        "FEM-based TI field calculations",
        "Enhanced simulation parameter control",
        "Multi-electrode montage support"
    ],
    "optimization": [
        "Evolutionary algorithm",
        "Exhaustive search algorithm", 
        "ROI-targeted stimulation",
        "Multi-objective optimization"
    ],
    "analysis": [
        "Atlas-based analysis",
        "Arbitrary ROI analysis",
    ],
    "visualization": [
        "Interactive NIfTI viewers",
        "3D mesh rendering",
        "Field overlay capabilities",
        "Publication-ready plots"
    ]
}


def get_version_info():
    """
    Get comprehensive version information for TI-Toolbox
    
    Returns:
        dict: Complete version information including tools, images, and capabilities
    """
    return {
        "ti_csc": TI_CSC_INFO,
        "docker_images": DOCKER_IMAGES,
        "tools": TOOLS_INFO,
        "system_requirements": SYSTEM_REQUIREMENTS,
        "capabilities": CAPABILITIES
    }


def get_version_string():
    """
    Get a simple version string
    
    Returns:
        str: Version string
    """
    return __version__


def get_tools_summary():
    """
    Get a summary of main neuroimaging tools
    
    Returns:
        dict: Summary of key tools with versions
    """
    key_tools = ["freesurfer", "simnibs", "fsl", "dcm2niix"]
    return {tool: TOOLS_INFO[tool] for tool in key_tools if tool in TOOLS_INFO} 
