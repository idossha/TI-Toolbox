@echo off
REM TI-Toolbox Analysis Setup Script for Windows
REM This script helps set up the streamlined analysis system

echo 🚀 Setting up TI-Toolbox Streamlined Analysis System
echo ==================================================

REM Check if we're in the right directory
if not exist "settings.yaml" (
    echo ❌ Error: settings.yaml not found. Please run this script from the analysis directory.
    exit /b 1
)

REM Check if virtual environment exists
if not exist "..\..\venv" (
    echo 📦 Creating virtual environment...
    python -m venv ..\..\venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call ..\..\venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
python -m pip install --upgrade pip
pip install -r ..\..\requirements.txt

REM Validate setup
echo ✅ Validating setup...
python main.py --validate-only

echo.
echo 🎉 Setup completed successfully!
echo.
echo Next steps:
echo 1. Run default analysis: python main.py
echo 2. Run all regions: python main.py --all-regions
echo 3. Run specific analysis: python main.py --region Left_Insula --optimization max
echo 4. See help: python main.py --help
echo.
echo Remember to activate the virtual environment:
echo ..\..\venv\Scripts\activate.bat

pause 