#!/bin/bash
# Install Blender in Docker container for electrode placement
set -e

echo "Installing Blender dependencies..."
apt-get update
apt-get install -y wget xz-utils libgl1 libglu1-mesa libxrender1 libxi6 libxkbcommon0 libxrandr2 libxinerama1 libxcursor1

echo "Downloading Blender 3.6.15 LTS..."
cd /tmp
wget https://download.blender.org/release/Blender3.6/blender-3.6.15-linux-x64.tar.xz

echo "Extracting Blender..."
tar -xf blender-3.6.15-linux-x64.tar.xz -C /opt

echo "Creating symlink..."
ln -sf /opt/blender-3.6.15-linux-x64/blender /usr/local/bin/blender

echo "Cleaning up..."
rm blender-3.6.15-linux-x64.tar.xz

echo "Verifying installation..."
blender --version

echo ""
echo "✓ Blender installed successfully!"
echo "  Location: /opt/blender-3.6.15-linux-x64/"
echo "  Executable: /usr/local/bin/blender"
