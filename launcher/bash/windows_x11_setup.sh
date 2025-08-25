#!/bin/bash

# Windows X11 Setup Helper Script
# This script helps configure X11 display forwarding on Windows systems

echo "==================================================================="
echo "Windows X11 Configuration Helper for TI-Toolbox"
echo "==================================================================="
echo ""

# Function to detect Windows environment
detect_windows_env() {
    case "$(uname -s)" in
        MINGW*)    echo "Git Bash" ;;
        MSYS*)     echo "MSYS2" ;;
        CYGWIN*)   echo "Cygwin" ;;
        *)         echo "Unknown" ;;
    esac
}

# Function to check if X server is running
check_x_server() {
    # Try to connect to the X server
    if command -v xset >/dev/null 2>&1; then
        if xset -q >/dev/null 2>&1; then
            echo "✓ X server appears to be running"
            return 0
        fi
    fi
    
    # Check common X server processes
    if tasklist.exe 2>/dev/null | grep -iE "(vcxsrv|xming|x410|xlaunch)" >/dev/null; then
        echo "✓ X server process detected"
        return 0
    fi
    
    echo "✗ No X server detected"
    return 1
}

# Function to get Windows host IP
get_windows_host_ip() {
    local ip=""
    
    # Method 1: PowerShell (most reliable)
    if command -v powershell.exe >/dev/null 2>&1; then
        ip=$(powershell.exe -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*' -and $_.InterfaceAlias -notlike '*vEthernet*'} | Select-Object -First 1).IPAddress" 2>/dev/null | tr -d '\r\n')
    fi
    
    # Method 2: WSL specific
    if [[ -z "$ip" ]] && [[ -f /proc/sys/kernel/osrelease ]] && grep -qi microsoft /proc/sys/kernel/osrelease; then
        ip=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}')
    fi
    
    # Method 3: hostname
    if [[ -z "$ip" ]]; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi
    
    # Method 4: Docker host
    if [[ -z "$ip" ]]; then
        ip="host.docker.internal"
    fi
    
    echo "$ip"
}

# Main setup process
echo "Detected Windows environment: $(detect_windows_env)"
echo ""

# Check for X server
echo "Checking for X server..."
if ! check_x_server; then
    echo ""
    echo "IMPORTANT: X server is not running!"
    echo ""
    echo "Please install and configure one of the following X servers:"
    echo ""
    echo "1. VcXsrv (Recommended)"
    echo "   - Download: https://sourceforge.net/projects/vcxsrv/"
    echo "   - Launch with: XLaunch.exe"
    echo "   - Settings:"
    echo "     * Display number: 0"
    echo "     * Multiple windows"
    echo "     * Start no client"
    echo "     * Disable access control (important!)"
    echo ""
    echo "2. Xming"
    echo "   - Download: https://sourceforge.net/projects/xming/"
    echo "   - Launch with: Xming.exe :0 -multiwindow -clipboard -ac"
    echo ""
    echo "3. X410 (Paid, from Microsoft Store)"
    echo "   - More user-friendly but costs money"
    echo ""
fi

# Get host IP
echo ""
echo "Detecting host IP address..."
HOST_IP=$(get_windows_host_ip)
echo "Host IP: $HOST_IP"

# Set and export DISPLAY
export DISPLAY="${HOST_IP}:0.0"
echo "DISPLAY set to: $DISPLAY"

# Create a config file for persistence
CONFIG_FILE="$HOME/.ti_csc_x11_config"
cat > "$CONFIG_FILE" << EOF
# TI-Toolbox X11 Configuration for Windows
export DISPLAY="${HOST_IP}:0.0"
export LIBGL_ALWAYS_SOFTWARE=1
export QT_X11_NO_MITSHM=1
EOF

echo ""
echo "Configuration saved to: $CONFIG_FILE"
echo ""
echo "==================================================================="
echo "SETUP COMPLETE"
echo ""
echo "To use this configuration in the future, run:"
echo "  source $CONFIG_FILE"
echo ""
echo "IMPORTANT REMINDERS:"
echo "1. Always start your X server before running Docker containers"
echo "2. Ensure 'Disable access control' is enabled in your X server"
echo "3. Windows Firewall may block connections - add exceptions if needed"
echo "4. If using WSL2, you may need to update DISPLAY after IP changes"
echo "===================================================================" 