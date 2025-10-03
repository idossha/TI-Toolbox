#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Use the guaranteed path from Dockerfile.ci
if command -v analyzer >/dev/null 2>&1; then
    ANALYZER_CMD="analyzer"
    echo "DEBUG: Found analyzer command in PATH"
else
    ANALYZER_CMD="/ti-toolbox/CLI/analyzer.sh"
    echo "DEBUG: Using guaranteed path from Dockerfile.ci: $ANALYZER_CMD"
fi

echo "DEBUG: ANALYZER_CMD = $ANALYZER_CMD"
echo "DEBUG: File exists: $([ -f "$ANALYZER_CMD" ] && echo "YES" || echo "NO")"

# Inputs:
# 1. Single Subject Analysis
# 2. Subject index (1)
# 3. Simulation index (1)
# 4. Space: mesh (1)
# 5. Analysis type: spherical (1)
# 6. Field file index (1)
# 7-9. Coordinates: -50, 0, 0
# 10. Radius: 10
# 11. Visualize: y
# 12. Confirm: y
INPUTS=$(cat <<'EOF'
1
1
1
1
1
1
-50
0
0
10
y
y
EOF
)

printf "%s\n" "$INPUTS" | "$ANALYZER_CMD"
