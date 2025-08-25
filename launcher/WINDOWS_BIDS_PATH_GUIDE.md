# Windows BIDS Directory Path Guide

## Overview
This guide helps Windows users properly set up their BIDS-compliant project directories for use with TI-Toolbox.

## Important Path Considerations

### 1. **Recommended Directory Locations**
For best compatibility, create your BIDS project directory in one of these locations:
- `C:\BIDS_projects\your_project_name`
- `C:\Users\YourUsername\Documents\BIDS_projects\your_project_name`
- Any path WITHOUT spaces or special characters

### 2. **Paths to Avoid**
Avoid these problematic path patterns:
- ❌ Paths with spaces: `C:\My Projects\BIDS data`
- ❌ OneDrive synced folders: `C:\Users\Username\OneDrive\...`
- ❌ Network drives: `\\server\share\...`
- ❌ Very long paths (>200 characters)

### 3. **Special Characters**
If your username or path contains special characters:
- Spaces are handled automatically but best avoided
- Avoid these characters: `< > : " | ? * [ ] ( ) & ^ % $ # @ ! ` ~ + = { }`
- Use only letters, numbers, underscores (_), and hyphens (-)

## Setting Up Your BIDS Directory

### Step 1: Create Project Directory
```batch
# Open Command Prompt as Administrator
mkdir C:\BIDS_projects
mkdir C:\BIDS_projects\my_study
```

### Step 2: Create BIDS Structure
Your directory should follow this structure:
```
C:\BIDS_projects\my_study\
├── sourcedata\
│   └── sub-101\
│       └── dicoms\
├── sub-101\
│   └── anat\
├── derivatives\
│   ├── SimNIBS\
│   └── freesurfer\
└── ti-toolbox\
    └── config\
```

### Step 3: Verify Permissions
Ensure you have full write permissions:
1. Right-click on your project folder
2. Select "Properties" → "Security" tab
3. Verify your user has "Full control"

## Docker Volume Mounting

The TI-Toolbox launcher automatically handles path conversion for Docker:
- Windows path: `C:\BIDS_projects\my_study`
- Converts to: `C:/BIDS_projects/my_study` (for Docker)
- Mounts as: `/mnt/my_study` (inside container)

## Troubleshooting

### Issue: "Invalid BIDS structure"
**Solution**: Ensure your directory follows the exact BIDS structure shown above.

### Issue: "Permission denied" errors
**Solutions**:
1. Run Docker Desktop as Administrator
2. Ensure your project directory has full write permissions
3. Disable Windows Defender folder protection for your project directory

### Issue: Path with spaces not working
**Solutions**:
1. Move project to a path without spaces
2. Or ensure the launcher properly quotes the path (handled automatically in v2.0.1+)

### Issue: OneDrive sync conflicts
**Solution**: Create project directories outside OneDrive-synced folders. Use:
```batch
# Create a non-synced location
mkdir C:\LocalProjects\BIDS_data
```

## Windows-Specific X11 Configuration

For GUI applications, ensure your X11 server (VcXsrv/Xming) is configured:
1. Launch VcXsrv with:
   - Display number: 0
   - "Disable access control" checked
   - "Multiple windows" mode
2. Windows Firewall: Allow VcXsrv through firewall
3. The launcher automatically sets `DISPLAY=host.docker.internal:0.0`

## Best Practices

1. **Use short, simple paths**: `C:\BIDS\study1` instead of `C:\Users\John Smith\My Documents\Research Projects\2024\Neuroimaging Study\`
2. **Avoid cloud-synced folders**: OneDrive, Dropbox, Google Drive can cause conflicts
3. **Test with a small dataset first**: Verify everything works before processing large datasets
4. **Keep paths consistent**: Don't move your project directory after starting processing

## Command Line Usage

If using Git Bash or WSL:
```bash
# Git Bash converts paths automatically
cd /c/BIDS_projects/my_study

# WSL2 requires mounting Windows drives
cd /mnt/c/BIDS_projects/my_study
```

## Further Help

If you encounter path-related issues:
1. Check the console output in the launcher for specific error messages
2. Verify your path doesn't contain problematic characters
3. Try creating a test project at `C:\test_bids` to isolate the issue
4. Contact support with your full path and error messages 