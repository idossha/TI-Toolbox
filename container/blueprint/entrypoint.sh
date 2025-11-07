#!/bin/bash

# Initialize .bashrc if it doesn't exist
touch ~/.bashrc

# Source environment setup scripts
[ -f "$FREESURFER_HOME/SetUpFreeSurfer.sh" ] && source "$FREESURFER_HOME/SetUpFreeSurfer.sh"

# Make CLI scripts executable
chmod +x /ti-toolbox/ti-toolbox/cli/*.sh

# Create CLI script aliases (without .sh extension)
alias GUI='GUI.sh'
alias analyzer='analyzer.sh'
alias ex-search='ex-search.sh'
alias flex-search='flex-search.sh'
alias group_analyzer='group_analyzer.sh'
alias movea='movea.sh'
alias pre-process='pre-process.sh'
alias simulator='simulator.sh'

# Add environment setup to .bashrc
{
    echo ""
    echo "source \"\$FREESURFER_HOME/SetUpFreeSurfer.sh\""
    echo ""
    echo "# TI-Toolbox CLI scripts"
    echo "export PATH=\"\$PATH:/ti-toolbox/ti-toolbox/cli\""
    echo "alias GUI='GUI.sh'"
    echo "alias analyzer='analyzer.sh'"
    echo "alias ex-search='ex-search.sh'"
    echo "alias flex-search='flex-search.sh'"
    echo "alias group_analyzer='group_analyzer.sh'"
    echo "alias movea='movea.sh'"
    echo "alias pre-process='pre-process.sh'"
    echo "alias simulator='simulator.sh'"
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
