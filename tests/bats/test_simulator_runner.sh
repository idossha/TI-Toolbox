#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v simulator >/dev/null 2>&1; then
    SIM_CMD="simulator"
else
    SIM_CMD="$SCRIPT_DIR/../../CLI/simulator.sh"
fi

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
