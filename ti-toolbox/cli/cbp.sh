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
if ! command -v simnibs_python &>/dev/null; then
    echo "Error: simnibs_python not found. Please ensure SimNIBS is properly installed."
    exit 1
fi
PYTHON_CMD="simnibs_python"

# Run the cluster permutation script with all arguments
exec "$PYTHON_CMD" "$STATS_DIR/cluster_permutation.py" "$@"

