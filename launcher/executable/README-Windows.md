# Windows Build Guide for TI-CSC

This guide addresses the Windows-specific build issues you may encounter when building the TI-CSC launcher.

## The Issue

On Windows, you may encounter an error like this when running `python build.py`:

```
ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory: 'C:\\Users\\...\\site-packages\\PyQt6\\Qt6\\qml\\QtQuick\\Controls\\FluentWinUI3\\light\\images\\pageindicatordelegate-indicator-delegate-current-hovered@2x.png'
```

This happens because PyQt6 has some files with extremely long paths that exceed Windows' default path length limit (260 characters).

## Solutions

### Solution 1: Use the Automated Fix Script (Recommended)

Run the automated fix script that tries multiple approaches:

```powershell
.\fix_windows_build.bat
```

This script will:
1. Try installing PyQt6 with user-specific flags
2. Fall back to PySide6 if PyQt6 fails  
3. Try alternative installation methods
4. Automatically run the build process if successful

### Solution 2: Enable Long Path Support (Advanced)

If you want to use PyQt6 specifically, enable Windows long path support:

1. **Run as Administrator**: Right-click on PowerShell and select "Run as Administrator"
2. **Execute the script**:
   ```powershell
   .\enable_long_paths.ps1
   ```
3. **Restart your computer** (may be required)
4. **Try building again**:
   ```powershell
   python build.py
   ```

### Solution 3: Manual Installation

Try installing dependencies manually with specific flags:

```powershell
# Option A: Install with PySide6 (recommended)
python -m pip install --user --no-warn-script-location PySide6>=6.6.0 pywin32>=306 winshell>=0.6 pyinstaller

# Option B: Install PyQt6 with user flag
python -m pip install --user --no-warn-script-location PyQt6>=6.6.0 PyQt6-Qt6>=6.6.0 pywin32>=306 winshell>=0.6 pyinstaller
```

Then run the build script:
```powershell
python build.py
```

### Solution 4: Use Windows Subsystem for Linux (WSL)

If you have WSL installed, you can build the Linux version instead:

1. Open WSL terminal
2. Navigate to your project directory
3. Run the normal build process (which works fine on Linux)

## What Changed?

The codebase has been updated with a compatibility layer (`src/qt_compat.py`) that allows the application to work with both PyQt6 and PySide6. This means:

- ✅ Works with PyQt6 (if you can install it)
- ✅ Works with PySide6 (recommended for Windows)
- ✅ Automatically detects which one is available
- ✅ No code changes needed in the main application

## Technical Details

### Why This Happens
- Windows has a default path length limit of 260 characters
- PyQt6 includes some files with very long paths
- Python's pip cannot create these files during installation

### Why PySide6 Works Better
- PySide6 is the official Qt binding for Python
- It doesn't have the same long path issues
- It's functionally equivalent to PyQt6
- It's actively maintained by the Qt Company

## Troubleshooting

### Still Getting Errors?

1. **Check Python version**: Ensure you're using Python 3.8+
   ```powershell
   python --version
   ```

2. **Update pip**:
   ```powershell
   python -m pip install --upgrade pip
   ```

3. **Clear pip cache**:
   ```powershell
   python -m pip cache purge
   ```

4. **Try with virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   python -m pip install --upgrade pip
   python -m pip install PySide6>=6.6.0 pyinstaller
   python build.py
   ```

### Need More Help?

- Check the main project README for general build instructions
- Open an issue on the project repository
- Make sure Docker Desktop is installed and running

## Summary

The easiest approach is to run `.\fix_windows_build.bat` which will automatically try different solutions and build your application. The codebase now supports both PyQt6 and PySide6, so you don't need to worry about which one gets installed. 