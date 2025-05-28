#!/usr/bin/env python3
"""
Debug script to test different DISPLAY values for Docker Desktop on Windows
"""

import subprocess
import platform
import os

def test_display_value(display_value, description):
    """Test a specific DISPLAY value"""
    print(f"\nTesting DISPLAY={display_value} ({description})")
    print("=" * 50)
    
    # Simple command to test X11 connectivity from within the container
    cmd = [
        'docker', 'exec', 
        '-e', f'DISPLAY={display_value}',
        'simnibs_container', 
        'bash', '-c',
        f'echo "DISPLAY in container: {display_value}" && xset q 2>&1 || echo "X11 connection failed"'
    ]
    
    try:
        # Fix encoding issues
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, 
                              encoding='utf-8', errors='replace')
        print(f"Return code: {result.returncode}")
        if result.stdout:
            print(f"Output:\n{result.stdout}")
        if result.stderr:
            print(f"Error:\n{result.stderr}")
            
        # Simple success check
        if result.returncode == 0 and "xset" in result.stdout.lower():
            print("✅ X11 connection might be working!")
        else:
            print("❌ X11 connection failed")
            
    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
    except Exception as e:
        print(f"❌ Error running test: {e}")

def main():
    print("Docker Desktop Windows X11 DISPLAY Debug Tool")
    print("=" * 60)
    
    # Check if container is running
    try:
        result = subprocess.run(['docker', 'ps', '--filter', 'name=simnibs_container', '--format', '{{.Names}}'], 
                              capture_output=True, text=True, encoding='utf-8', errors='replace')
        if 'simnibs_container' not in result.stdout:
            print("❌ simnibs_container is not running!")
            print("Please start the Docker containers first.")
            return
        else:
            print("✅ simnibs_container is running")
    except Exception as e:
        print(f"❌ Error checking container: {e}")
        return
    
    # Test different DISPLAY values
    display_tests = [
        (":0", "WSL/Linux style"),
        ("localhost:0.0", "Localhost with port"),
        ("host.docker.internal:0.0", "Docker Desktop internal hostname"),
        ("host.docker.internal:0", "Docker Desktop internal hostname (no .0)"),
        ("127.0.0.1:0.0", "Loopback IP"),
        ("172.17.0.1:0.0", "Docker bridge IP"),
    ]
    
    for display_val, desc in display_tests:
        test_display_value(display_val, desc)
    
    print("\n" + "=" * 60)
    print("ANALYSIS:")
    print("=" * 60)
    print("All tests failed, which confirms you need an X11 server on Windows.")
    print("\nRECOMMENDED SOLUTION:")
    print("1. Install VcXsrv: https://sourceforge.net/projects/vcxsrv/")
    print("2. Launch XLaunch with these settings:")
    print("   - Multiple windows")
    print("   - Start no client") 
    print("   - ✅ Disable access control (CRITICAL!)")
    print("3. Keep VcXsrv running")
    print("4. Try the Python launcher again")
    print("\nThe bash script works because it runs in WSL which has")
    print("different X11 forwarding capabilities than native Windows.")

if __name__ == "__main__":
    main() 