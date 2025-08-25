@echo off
echo 🚀 TI-Toolbox Windows Build Fix
echo ==================================================

echo 🖥️  Platform: Windows
echo 🐍 Python: Using system Python

echo.
echo 📦 Attempting to fix PyQt6 installation issues...

REM Option 1: Try installing with --user and --no-warn-script-location
echo Trying Option 1: PyQt6 with user installation...
python -m pip install --user --no-warn-script-location PyQt6>=6.6.0 PyQt6-Qt6>=6.6.0 pywin32>=306 winshell>=0.6 pyinstaller

if %ERRORLEVEL% EQU 0 (
    echo ✅ Option 1 successful! PyQt6 installed.
    goto :build
)

echo ❌ Option 1 failed. Trying Option 2...

REM Option 2: Try PySide6 instead
echo Trying Option 2: PySide6 instead of PyQt6...
python -m pip install --user --no-warn-script-location PySide6>=6.6.0 pywin32>=306 winshell>=0.6 pyinstaller

if %ERRORLEVEL% EQU 0 (
    echo ✅ Option 2 successful! PySide6 installed.
    goto :build
)

echo ❌ Option 2 failed. Trying Option 3...

REM Option 3: Try with specific pip version and cache settings
echo Trying Option 3: Clean installation with cache disabled...
python -m pip install --upgrade pip
python -m pip install --user --no-cache-dir --no-warn-script-location PySide6>=6.6.0 pywin32>=306 winshell>=0.6 pyinstaller

if %ERRORLEVEL% EQU 0 (
    echo ✅ Option 3 successful! Dependencies installed.
    goto :build
)

echo ❌ All options failed. Please see solutions below:
echo.
echo 💡 SOLUTIONS:
echo 1. Run PowerShell as Administrator and execute: .\enable_long_paths.ps1
echo 2. Or manually enable long paths in Windows settings
echo 3. Or use the Windows Subsystem for Linux (WSL)
echo.
echo For more help, see: https://docs.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation
echo.
pause
exit /b 1

:build
echo.
echo 🏗️  Dependencies installed successfully!
echo Now running the build script...
python build.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo 🎉 Build completed successfully!
) else (
    echo.
    echo ❌ Build failed. Check the output above for details.
)

echo.
pause 