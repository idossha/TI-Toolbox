# New Project Setup

This directory contains files and configurations that are used when initializing a new TI-Toolbox project. It serves as a template and initialization system for new projects.

## Contents

### Configuration Files
Located in `configs/`:
- Default configuration files for various tools (pre-processing, simulation, search, etc.)
- These files are copied to the new project's `code/tit/config` directory when a project is first created

### First Time User Experience
`first_time_user.py`:
- Manages the first-time user experience in the TI-Toolbox GUI
- Shows a welcome message to new users
- Tracks whether the user has seen the welcome message
- Integrates with example data setup for new projects
- Uses the project status system to maintain user preferences

### Example Data Manager
`example_data_manager.py`:
- Automatically copies example data (ernie and MNI152 subjects) to new projects
- Only runs for brand new projects (no existing subject directories)
- Creates BIDS-compliant directory structure
- Tracks example data status in project metadata
- Can be run standalone or integrated with the GUI startup

## How It Works

1. When a new project is created:
   - The loader script (`loader.sh` or `dev/bash_dev/loader_dev.sh`) checks if the project is new
   - If new, it copies all configuration files from `configs/` to the project
   - Creates a project status file (`derivatives/ti-toolbox/.ti-toolbox-info/project_status.json`) with initial flags
   - Initializes BIDS directory structure
   - Creates dataset_description.json and README files
   - Calls `example_data_manager.py` to copy example data if applicable

2. When the GUI starts:
   - Checks the project status file for the `show_welcome` flag
   - If true, shows the welcome message to new users
   - Checks if example data needs to be copied (for projects created outside the loader)
   - Allows users to opt out of seeing the message again
   - Updates the project status file accordingly

## Project Status File

The project status file (`derivatives/ti-toolbox/.ti-toolbox-info/project_status.json`) contains:
```json
{
  "project_created": "2024-01-01T12:00:00.000000",
  "last_updated": "2024-01-01T12:00:00.000000",
  "config_created": true,
  "example_data_copied": false,
  "user_preferences": {
    "show_welcome": true
  },
  "project_metadata": {
    "name": "my_project",
    "path": "/path/to/my_project",
    "version": "2.1.3"
  },
  "example_subjects": ["sub-ernie", "sub-MNI152"],
  "example_data_timestamp": "2024-01-01T12:00:00.000000"
}
```

## BIDS Directory Structure

The initialization creates the following BIDS-compliant structure:
```
project/
├── sourcedata/                          # Raw DICOM files (user-provided)
├── sub-{subject}/                       # Subject-level data (BIDS format)
│   └── anat/                           # Anatomical images
├── derivatives/                         # Processed data
│   ├── tit/                     # TI-Toolbox outputs
│   │   └── .tit-info/          # Hidden metadata directory
│   │       ├── project_status.json    # Project status tracking
│   │       └── system_info.txt        # System information
│   ├── SimNIBS/                        # SimNIBS outputs
│   └── freesurfer/                     # FreeSurfer outputs
├── code/                                # Code and configurations
│   └── tit/
│       └── config/                     # Configuration files
├── dataset_description.json             # BIDS dataset description
└── README                               # BIDS README file
```

## Example Data

For new projects, the following example data is automatically copied:
- **sub-ernie**: SimNIBS example subject with T1w and T2w anatomical scans
- **sub-MNI152**: Standard MNI152 template for reference

Example data is only copied if:
- No subject directories exist in the project
- The project status doesn't indicate example data was already copied
- No user data is present in sourcedata/

## Adding New Features

To add new features to the new project setup:
1. Add new configuration files to `configs/`
2. Update the loader scripts to handle new files
3. Add new flags to the project status file if needed
4. Update the `example_data_manager.py` if new example data is added
5. Update this documentation
