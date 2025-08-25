#!/usr/bin/env python3
"""
Package TI-Toolbox for distribution to colleagues
Creates a clean folder with just the executable and user guide
"""

import os
import shutil
import platform
import sys
from datetime import datetime

def create_distribution_package():
    """Create a distribution package"""
    
    system = platform.system()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Determine executable name and package folder
    if system == "Darwin":  # macOS
        # Prioritize .app bundle over raw executable
        if os.path.exists("dist/TI-Toolbox.app"):
            exe_name = "TI-Toolbox.app"
            exe_source = "dist/TI-Toolbox.app"
            is_app_bundle = True
        else:
            exe_name = "TI-Toolbox"
            exe_source = "dist/TI-Toolbox"
            is_app_bundle = False
        package_name = f"TI-Toolbox_macOS_{timestamp}"
    elif system == "Windows":
        exe_name = "TI-Toolbox.exe"
        exe_source = f"dist/{exe_name}"
        package_name = f"TI-Toolbox_Windows_{timestamp}"
        is_app_bundle = False
    else:  # Linux
        exe_name = "TI-Toolbox"
        exe_source = f"dist/{exe_name}"
        package_name = f"TI-Toolbox_Linux_{timestamp}"
        is_app_bundle = False
    
    print(f"📦 Creating distribution package: {package_name}")
    
    # Create package directory
    if os.path.exists(package_name):
        shutil.rmtree(package_name)
    os.makedirs(package_name)
    
    # Check if executable exists
    if not os.path.exists(exe_source):
        print(f"❌ Executable not found: {exe_source}")
        print("Please run 'python build.py' first to create the executable")
        return False
    
    # Copy executable
    if is_app_bundle:
        print(f"📱 Copying app bundle...")
        shutil.copytree(exe_source, os.path.join(package_name, exe_name))
    else:
        print(f"💻 Copying executable...")
        shutil.copy2(exe_source, os.path.join(package_name, exe_name))
        
        # Make executable on Unix systems
        if system in ["Darwin", "Linux"]:
            os.chmod(os.path.join(package_name, exe_name), 0o755)
    
    # Copy user documentation
    if os.path.exists("README_FOR_USERS.md"):
        print(f"📖 Copying user guide...")
        shutil.copy2("README_FOR_USERS.md", package_name)
    
    # Create a simple text instruction file
    instructions = f"""TI-Toolbox - Quick Start Guide

Prerequisites:
1. Install Docker Desktop from https://docker.com
2. Start Docker Desktop and wait for it to fully load
3. For GUI functionality, install X server:
   - macOS: XQuartz (https://www.xquartz.org/)
   - Windows: VcXsrv or similar X server
   - Linux: X11 usually pre-installed

How to Use:
1. Double-click {exe_name}
2. Click "📋 System Requirements" for detailed system information
3. Select your project directory using the "Browse" button
4. Click "❓ Help" for BIDS directory structure guide
5. Use the toggle switch to start Docker containers (🐋 Start → 🛑 Stop)
6. Use "🖥️ Launch CLI" or "🖼️ Launch GUI" buttons as needed

Built-in Help:
- System Requirements popup: Comprehensive setup and performance information
- BIDS Structure Help: Detailed guide for project directory setup
- Color-coded console: Real-time status and error messages

System Requirements:
- 32GB+ RAM minimum for full functionality
- 30GB+ free disk space for Docker images
- X server required for GUI (CLI works without it)

For detailed instructions, see README_FOR_USERS.md

Need help? Contact your system administrator.

Built on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} for {system}
TI-Toolbox: Temporal Interference Computational Stimulation Consortium
"""
    
    with open(os.path.join(package_name, "QUICK_START.txt"), 'w') as f:
        f.write(instructions)
    
    # Get package size
    def get_size(path):
        if os.path.isfile(path):
            return os.path.getsize(path)
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                total += os.path.getsize(os.path.join(dirpath, filename))
        return total
    
    package_size = get_size(package_name)
    size_mb = package_size / (1024 * 1024)
    
    print(f"✅ Distribution package created successfully!")
    print(f"📁 Package: {package_name}/")
    print(f"📊 Size: {size_mb:.1f} MB")
    print(f"📋 Contents:")
    
    for item in os.listdir(package_name):
        item_path = os.path.join(package_name, item)
        if os.path.isdir(item_path):
            print(f"   📁 {item}/ (app bundle)")
        else:
            item_size = os.path.getsize(item_path) / (1024 * 1024)
            print(f"   📄 {item} ({item_size:.1f} MB)")
    
    print(f"\n🚀 Ready for distribution!")
    
    if system == "Darwin":
        print(f"   🍎 macOS: Share the '{package_name}' folder")
        print(f"   ✅ Users double-click {exe_name} - no terminal window!")
    elif system == "Windows":
        print(f"   🪟 Windows: Share the '{package_name}' folder")
        print(f"   ✅ Users double-click {exe_name} - clean GUI launch!")
    else:
        print(f"   🐧 Linux: Share the '{package_name}' folder")
        print(f"   ✅ Users double-click {exe_name} or run from terminal")
    
    print(f"   📋 Recipients only need Docker Desktop installed")
    
    return True

def main():
    print("📦 TI-Toolbox Distribution Packager")
    print("=" * 50)
    
    if not os.path.exists("dist"):
        print("❌ No 'dist' folder found. Please run 'python build.py' first.")
        sys.exit(1)
    
    if create_distribution_package():
        print("\n✨ Packaging completed successfully!")
    else:
        print("\n❌ Packaging failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 