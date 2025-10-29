#!/bin/bash
#
# Cluster-Based Permutation Testing CLI wrapper
# Provides easy command-line access to permutation testing
#
# Usage: ./cbp.sh --csv subjects.csv --name my_analysis [options]
#

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATS_DIR="$SCRIPT_DIR/../stats"

# Check if running in SimNIBS environment
if command -v simnibs_python &>/dev/null; then
    PYTHON_CMD="simnibs_python"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    echo "Error: Python not found. Please ensure SimNIBS is installed or python3 is available."
    exit 1
fi

# Run the cluster permutation script with all arguments
exec "$PYTHON_CMD" "$STATS_DIR/cluster_permutation.py" "$@"

