#!/bin/bash

# Initialize .bashrc if it doesn't exist
touch ~/.bashrc

# Source environment setup scripts
[ -f "$FREESURFER_HOME/SetUpFreeSurfer.sh" ] && source "$FREESURFER_HOME/SetUpFreeSurfer.sh"

# Add environment setup to .bashrc
{
    echo ""
    echo "source \"\$FREESURFER_HOME/SetUpFreeSurfer.sh\""
} >> ~/.bashrc

# Setup XDG runtime directory
export XDG_RUNTIME_DIR=/tmp/runtime-root
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# ============================================================================
# Container-side initialization - minimal setup only
# ============================================================================
# Note: Project initialization now handled by loader.sh before container starts

# Start interactive shell if no command provided
if [ $# -eq 0 ]; then
    exec /bin/bash
else
    exec "$@"
fi
