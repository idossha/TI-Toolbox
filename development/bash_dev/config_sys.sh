
#!/bin/bash

# Function to check for macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        echo "This script only runs on macOS. Aborting."
        exit 1
    else
        echo "macOS detected. Proceeding..."
    fi
}

# Function to check XQuartz version
check_xquartz_version() {
    XQUARTZ_APP="/Applications/Utilities/XQuartz.app"
    if [ ! -d "$XQUARTZ_APP" ]; then
        echo "XQuartz is not installed. Please install XQuartz 2.7.7."
        exit 1
    else
        xquartz_version=$(mdls -name kMDItemVersion "$XQUARTZ_APP" | awk -F'"' '{print $2}')
        echo "XQuartz version detected: $xquartz_version"
        if [[ "$xquartz_version" > "2.8.0" ]]; then
            echo "Warning: XQuartz version is above 2.8.0. Please downgrade to version 2.7.7 for compatibility."
            exit 1
        else
            echo "XQuartz version is compatible."
        fi
    fi
}

# Function to allow connections from network clients
allow_network_clients() {
    echo "Enabling connections from network clients in XQuartz..."
    defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false
    open -a XQuartz
    sleep 2
}
# changed `export DISPLAY=localhost:0` to `export DISPLAY=:0`
# Potential explanation: When you set DISPLAY=localhost:0, it tells X11 applications to connect to the X server via TCP on localhost (which is 127.0.0.1) at display 0. However, by default, XQuartz uses UNIX domain sockets and does not listen on TCP ports unless explicitly configured to do so.
setup_x11_display() {
    echo "Setting DISPLAY to :0"
    export DISPLAY=:0

    echo "Allowing X11 connections from localhost..."
    xhost +localhost

    echo "Allowing X11 connections from the hostname..."
    xhost +$(hostname)
}

# Main script
echo "Checking if system is macOS..."
check_macos

echo "Checking XQuartz installation and version..."
check_xquartz_version

echo "Proceeding to configure XQuartz..."
allow_network_clients

echo "Setting up X11 display and connections..."
setup_x11_display

echo "Setup complete. X11 is ready to use."
