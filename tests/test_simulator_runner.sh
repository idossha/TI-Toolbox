#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "DEBUG: SCRIPT_DIR = $SCRIPT_DIR"
echo "DEBUG: Looking for simulator.sh..."

if command -v simulator >/dev/null 2>&1; then
    SIM_CMD="simulator"
    echo "DEBUG: Found simulator command in PATH"
else
    # Fix path resolution for Docker container
    if [ -f "/development/CLI/simulator.sh" ]; then
        SIM_CMD="/development/CLI/simulator.sh"
        echo "DEBUG: Found simulator.sh at /development/CLI/simulator.sh"
    elif [ -f "$SCRIPT_DIR/../CLI/simulator.sh" ]; then
        SIM_CMD="$SCRIPT_DIR/../CLI/simulator.sh"
        echo "DEBUG: Found simulator.sh at $SCRIPT_DIR/../CLI/simulator.sh"
    else
        SIM_CMD="$SCRIPT_DIR/../../CLI/simulator.sh"
        echo "DEBUG: Using fallback path: $SCRIPT_DIR/../../CLI/simulator.sh"
    fi
fi

echo "DEBUG: SIM_CMD = $SIM_CMD"
echo "DEBUG: File exists: $([ -f "$SIM_CMD" ] && echo "YES" || echo "NO")"

# 1st subject
# isotropic
# montage mode
# unipolar
# skip conductivity edits
# eeg net
# montage
# electrode shape
# electrode dimensions
# electrode thickness
# intensity
# confirm parameters
INPUTS=$(cat <<'EOF'
1 
1
1
U
0
1
4
rect
2,2
2
10
y
EOF
)

printf "%s\n" "$INPUTS" | "$SIM_CMD"
