#!/usr/bin/env python3
"""
Windows X11 Server Test Script
This script helps Windows users verify their X11 server setup before using the TI-CSC GUI.
"""

import subprocess
import platform
import sys
import os
import time

def run_command(cmd, timeout=5):
    """Run a command with timeout"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def test_x11_server():
    """Test X11 server setup on Windows"""
    print("=" * 60)
    print("TI-CSC Windows X11 Server Test")
    print("=" * 60)
    
    if platform.system() != "Windows":
        print("❌ This script is only for Windows")
        return False
    
    print("🔍 Checking for running X11 servers...")
    
    # Check for VcXsrv process
    print("\n1. Checking for VcXsrv...")
    code, stdout, stderr = run_command('tasklist /FI "IMAGENAME eq vcxsrv.exe" /FO CSV')
    if code == 0 and "vcxsrv.exe" in stdout:
        print("✅ VcXsrv is running")
        vcxsrv_running = True
    else:
        print("❌ VcXsrv not found")
        vcxsrv_running = False
    
    # Check for Xming process
    print("\n2. Checking for Xming...")
    code, stdout, stderr = run_command('tasklist /FI "IMAGENAME eq Xming.exe" /FO CSV')
    if code == 0 and "Xming.exe" in stdout:
        print("✅ Xming is running")
        xming_running = True
    else:
        print("❌ Xming not found")
        xming_running = False
    
    # Check for X11 ports
    print("\n3. Checking X11 ports (6000-6010)...")
    x11_port_found = False
    for port in range(6000, 6011):
        code, stdout, stderr = run_command(f'netstat -an | findstr ":{port}"')
        if code == 0 and stdout.strip():
            print(f"✅ Port {port} is in use (likely X11 server)")
            x11_port_found = True
            break
    
    if not x11_port_found:
        print("❌ No X11 ports found")
    
    # Check DISPLAY environment variable
    print("\n4. Checking DISPLAY environment variable...")
    display_var = os.environ.get("DISPLAY")
    if display_var:
        print(f"✅ DISPLAY is set to: {display_var}")
    else:
        print("ℹ️  DISPLAY not set (this is normal for Windows)")
    
    # Overall assessment
    print("\n" + "=" * 60)
    print("ASSESSMENT:")
    print("=" * 60)
    
    if vcxsrv_running or xming_running or x11_port_found:
        print("✅ X11 server appears to be running!")
        print("Your system should be ready for TI-CSC GUI.")
        return True
    else:
        print("❌ No X11 server detected")
        print("\nRECOMMENDED ACTION:")
        print("1. Install VcXsrv from: https://sourceforge.net/projects/vcxsrv/")
        print("2. Run 'XLaunch' and configure it:")
        print("   - Multiple windows")
        print("   - Start no client")
        print("   - Disable access control")
        print("3. Keep VcXsrv running while using TI-CSC")
        print("\nAlternatively, install and run Xming")
        return False

def test_docker():
    """Test Docker setup"""
    print("\n" + "=" * 60)
    print("BONUS: Docker Test")
    print("=" * 60)
    
    print("🔍 Checking Docker installation...")
    code, stdout, stderr = run_command('docker --version')
    if code == 0:
        print(f"✅ Docker installed: {stdout.strip()}")
        
        print("\n🔍 Checking Docker daemon...")
        code, stdout, stderr = run_command('docker info')
        if code == 0:
            print("✅ Docker daemon is running")
        else:
            print("❌ Docker daemon not running or not accessible")
            print("💡 Try starting Docker Desktop")
    else:
        print("❌ Docker not found")
        print("💡 Install Docker Desktop from: https://www.docker.com/products/docker-desktop/")

if __name__ == "__main__":
    success = test_x11_server()
    test_docker()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Your system appears ready for TI-CSC GUI!")
    else:
        print("⚠️  Please set up an X11 server before using TI-CSC GUI")
    print("=" * 60)
    
    input("\nPress Enter to exit...") 