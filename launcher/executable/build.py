#!/usr/bin/env python3
"""
Cross-platform build script for TI-CSC
This script will create an executable for the current platform.
"""

import subprocess
import sys
import os
import platform
import shutil

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n📦 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        print(f"✅ {description} completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed!")
        print(f"Error: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        return False

def convert_icons():
    """Convert PNG icon to platform-specific formats"""
    if not os.path.exists("icon.png"):
        print("⚠️  No icon.png found - building without custom icon")
        return True
    
    print("\n🎨 Converting icon.png to executable formats...")
    cmd = f"{sys.executable} convert_icon.py"
    return run_command(cmd, "Converting icons")

def install_dependencies():
    """Install required dependencies"""
    # Use Windows-specific requirements file on Windows to avoid PyQt6 path length issues
    system = platform.system()
    requirements_file = "requirements-windows.txt" if system == "Windows" else "requirements.txt"
    
    commands = [
        (f"{sys.executable} -m pip install --upgrade pip", "Upgrading pip"),
        (f"{sys.executable} -m pip install -r {requirements_file}", "Installing Qt dependencies"),
        (f"{sys.executable} -m pip install pyinstaller", "Installing PyInstaller"),
    ]
    
    for cmd, desc in commands:
        if not run_command(cmd, desc):
            return False
    return True

def check_required_files():
    """Check if all required files are present"""
    required_files = [
        "src/ti_csc_launcher.py",
        "src/dialogs.py",
        "src/shortcuts_manager.py",
        "src/qt_compat.py",
        "docker-compose.yml",
        "requirements.txt",
        "requirements-windows.txt",
        "ti_csc_launcher.spec"
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   • {file}")
        return False
    return True

def build_executable():
    """Build the executable using PyInstaller"""
    # Clean previous builds
    for dir_name in ['build', 'dist', '__pycache__', 'src/__pycache__']:
        if os.path.exists(dir_name):
            print(f"🧹 Cleaning {dir_name}...")
            shutil.rmtree(dir_name)
    
    # Build using the spec file
    cmd = f"{sys.executable} -m PyInstaller ti_csc_launcher.spec --clean"
    return run_command(cmd, "Building executable with PyInstaller")

def main():
    """Main build process"""
    print("🚀 TI-CSC Build Script")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required!")
        sys.exit(1)
    
    # Display system info
    system = platform.system()
    arch = platform.machine()
    print(f"🖥️  Platform: {system} {arch}")
    print(f"🐍 Python: {sys.version}")
    
    # Check required files
    if not check_required_files():
        print("❌ Missing required files!")
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        print("❌ Failed to install dependencies!")
        sys.exit(1)
    
    # Convert icons
    if not convert_icons():
        print("❌ Failed to convert icons!")
        sys.exit(1)
    
    # Build executable
    if not build_executable():
        print("❌ Failed to build executable!")
        sys.exit(1)
    
    # Show results
    print("\n🎉 Build completed successfully!")
    print("=" * 50)
    
    dist_path = os.path.join(os.getcwd(), "dist")
    if system == "Darwin":  # macOS
        app_path = os.path.join(dist_path, "TI-CSC.app")
        if os.path.exists(app_path):
            print(f"📱 macOS App Bundle: {app_path}")
            print("   ✅ This is what you distribute to macOS users!")
            print("   ✅ No terminal window - launches directly to GUI")
            print("   ✅ Custom icon included")
            print("   💡 Users just double-click the .app file")
        exe_path = os.path.join(dist_path, "TI-CSC")
        if os.path.exists(exe_path):
            print(f"💻 Raw Executable: {exe_path}")
            print("   ⚠️  This may show terminal - use .app instead")
    elif system == "Windows":
        exe_path = os.path.join(dist_path, "TI-CSC.exe")
        if os.path.exists(exe_path):
            print(f"💻 Windows Executable: {exe_path}")
            print("   ✅ This is what you distribute to Windows users!")
            print("   ✅ No console window - launches directly to GUI")
            print("   ✅ Custom icon included")
            print("   💡 Users just double-click the .exe file")
    else:  # Linux
        exe_path = os.path.join(dist_path, "TI-CSC")
        if os.path.exists(exe_path):
            print(f"💻 Linux Executable: {exe_path}")
            print("   ✅ This is what you distribute to Linux users!")
            print("   ✅ Custom icon included")
            print("   💡 Users just double-click or run from terminal")
    
    print("\n📋 Distribution Summary:")
    print("   • The executable includes all dependencies")
    print("   • Recipients need Docker Desktop installed and running")
    print("   • No Python installation required on target machines")
    print("   • Clean GUI launch - no terminal windows")
    print("   • Built-in help system with system requirements and BIDS guide")
    print("   • Enhanced Docker detection and error handling")
    print("   • Professional toggle controls and status indicators")
    
    if system == "Darwin":
        print(f"\n🍎 macOS Distribution:")
        print(f"   Just share: TI-CSC.app")
        print(f"   Recipients also need: XQuartz for GUI functionality")
    elif system == "Windows":
        print(f"\n🪟 Windows Distribution:")
        print(f"   Just share: TI-CSC.exe")
        print(f"   Recipients also need: VcXsrv or similar X server for GUI")
    else:
        print(f"\n🐧 Linux Distribution:")
        print(f"   Just share: TI-CSC (make sure it's executable)")
        print(f"   Recipients may need: xhost +local:docker for GUI")

if __name__ == "__main__":
    main() 