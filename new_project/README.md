# New Project Setup

This directory contains files and configurations that are used when initializing a new TI-Toolbox project. It serves as a template and initialization system for new projects.

## Contents

### Configuration Files
Located in `configs/`:
- Default configuration files for various tools (pre-processing, simulation, search, etc.)
- These files are copied to the new project's `code/ti-toolbox/config` directory when a project is first created

### First Time User Experience
`first_time_user.py`:
- Manages the first-time user experience in the TI-Toolbox GUI
- Shows a welcome message to new users
- Tracks whether the user has seen the welcome message
- Uses the project status system to maintain user preferences

## How It Works

1. When a new project is created:
   - The loader script (`development/loader/loader_dev.sh`) checks if the project is new
   - If new, it copies all configuration files from `configs/` to the project
   - Creates a project status file (`sourcedata/.ti-toolbox-info/project_status.json`) with initial flags

2. When the GUI starts:
   - Checks the project status file for the `gui_explain` flag
   - If true, shows the welcome message to new users
   - Allows users to opt out of seeing the message again
   - Updates the project status file accordingly

## Project Status File

The project status file (`sourcedata/.ti-toolbox-info/project_status.json`) contains:
```json
{
  "config_created": true,    // Whether default configs were copied
  "gui_explain": true,       // Whether to show the welcome message
  "last_updated": "..."      // Timestamp of last update
}
```

## Adding New Features

To add new features to the new project setup:
1. Add new configuration files to `configs/`
2. Update the loader script to handle new files
3. Add new flags to the project status file if needed
4. Update this documentation
