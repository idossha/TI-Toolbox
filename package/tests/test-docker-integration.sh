#!/bin/bash

# Test Docker integration for TI-Toolbox Electron app
set -e

echo "Testing Docker integration..."

# Test 1: Docker availability
echo "1. Checking Docker..."
if command -v docker &> /dev/null; then
    echo "   ✓ Docker found at: $(which docker)"
    echo "   ✓ Docker version: $(docker version --format '{{.Server.Version}}')"
else
    echo "   ✗ Docker not found in PATH"
    echo "   PATH: $PATH"
fi

# Test 2: Docker Compose availability
echo ""
echo "2. Checking Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo "   ✓ docker-compose found at: $(which docker-compose)"
    echo "   ✓ Version: $(docker-compose version --short)"
elif docker compose version &> /dev/null; then
    echo "   ✓ docker compose plugin found"
    echo "   ✓ Version: $(docker compose version)"
else
    echo "   ✗ Docker Compose not found"
fi

# Test 3: X11/XQuartz on macOS
echo ""
echo "3. Checking X11/Display setup..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "   Platform: macOS"
    if command -v xhost &> /dev/null; then
        echo "   ✓ xhost found at: $(which xhost)"
        # Check if XQuartz is running
        if pgrep -x "XQuartz" > /dev/null; then
            echo "   ✓ XQuartz is running"
        else
            echo "   ✗ XQuartz is not running"
            echo "     Run: open -a XQuartz"
        fi
        # Check DISPLAY variable
        if [ -n "$DISPLAY" ]; then
            echo "   ✓ DISPLAY=$DISPLAY"
        else
            echo "   ✗ DISPLAY not set"
            echo "     Try: export DISPLAY=:0"
        fi
    else
        echo "   ✗ xhost not found (XQuartz may not be installed)"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "   Platform: Linux"
    if [ -n "$DISPLAY" ]; then
        echo "   ✓ DISPLAY=$DISPLAY"
    else
        echo "   ✗ DISPLAY not set"
    fi
else
    echo "   Platform: $OSTYPE"
fi

# Test 4: Docker directory structure
echo ""
echo "4. Checking package structure..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker/docker-compose.yml" ]; then
    echo "   ✓ docker-compose.yml found"
else
    echo "   ✗ docker-compose.yml not found at $SCRIPT_DIR/docker/"
fi

# Test 5: Container connectivity test
echo ""
echo "5. Testing container connectivity..."
if docker ps &> /dev/null; then
    echo "   ✓ Docker daemon is accessible"
    
    # Check if our containers exist
    if docker ps -a | grep -q "simnibs_container\|freesurfer_container"; then
        echo "   ! TI-Toolbox containers already exist"
        docker ps -a | grep "simnibs_container\|freesurfer_container" | sed 's/^/     /'
    else
        echo "   ✓ No existing TI-Toolbox containers"
    fi
else
    echo "   ✗ Cannot connect to Docker daemon"
fi

echo ""
echo "Test complete!"