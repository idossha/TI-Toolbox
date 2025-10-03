#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Use the guaranteed path from Dockerfile.ci
if command -v simulator >/dev/null 2>&1; then
    SIM_CMD="simulator"
    echo "DEBUG: Found simulator command in PATH"
else
    SIM_CMD="/ti-toolbox/CLI/simulator.sh"
    echo "DEBUG: Using guaranteed path from Dockerfile.ci: $SIM_CMD"
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
