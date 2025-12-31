#!/bin/bash

# Initialize .bashrc if it doesn't exist
touch ~/.bashrc

# Source environment setup scripts
[ -f "$FREESURFER_HOME/SetUpFreeSurfer.sh" ] && source "$FREESURFER_HOME/SetUpFreeSurfer.sh"

# Ensure `tit` is importable system-wide in the SimNIBS python environment.
# This fixes running python entrypoints by path like:
#   simnibs_python /ti-toolbox/tit/cli/simulator.py
if command -v simnibs_python >/dev/null 2>&1; then
    if ! simnibs_python -c "import tit" >/dev/null 2>&1; then
        # Editable install keeps imports working while still allowing mounted code changes.
        simnibs_python -m pip install -e /ti-toolbox >/dev/null 2>&1 || true
    fi
fi

# ============================================================================
# Software Version Checks and Display
# ============================================================================

print_software_info() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  TI-Toolbox Container - Software Environment"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
    
    # Get TI-Toolbox version from container image tag (set during build)
    TI_VERSION="${TI_TOOLBOX_VERSION:-unknown}"
    echo "✓ TI-Toolbox:     ${TI_VERSION}"
    
    # Check SimNIBS
    if command -v simnibs_python >/dev/null 2>&1; then
        SIMNIBS_VERSION=$(simnibs_python -c "import simnibs; print(simnibs.__version__)" 2>/dev/null || echo "unknown")
        echo "✓ SimNIBS:        v${SIMNIBS_VERSION}"
    else
        echo "✗ SimNIBS:        Not found"
    fi
    
    # Check FreeSurfer
    if [ -n "$FREESURFER_HOME" ] && [ -d "$FREESURFER_HOME" ]; then
        if [ -f "$FREESURFER_HOME/build-stamp.txt" ]; then
            FS_VERSION=$(cat "$FREESURFER_HOME/build-stamp.txt" 2>/dev/null | head -n1 | awk '{print $1}' || echo "unknown")
        else
            FS_VERSION=$(cat "$FREESURFER_HOME/VERSION" 2>/dev/null || echo "unknown")
        fi
        echo "✓ FreeSurfer:     ${FS_VERSION}"
    else
        echo "✗ FreeSurfer:     Not configured"
    fi
    
    # Check dcm2niix
    if command -v dcm2niix >/dev/null 2>&1; then
        DCM2NIIX_VERSION=$(dcm2niix --version 2>&1 | head -n1 | awk '{print $2}' || echo "unknown")
        echo "✓ dcm2niix:       ${DCM2NIIX_VERSION}"
    else
        echo "✗ dcm2niix:       Not found"
    fi
    
    # Check Neovim
    if command -v nvim >/dev/null 2>&1; then
        NVIM_VERSION=$(nvim --version 2>&1 | head -n1 | awk '{print $2}')
        echo "✓ Neovim:         ${NVIM_VERSION}"
    else
        echo "✗ Neovim:         Not found"
    fi
    
    # Check tmux
    if command -v tmux >/dev/null 2>&1; then
        TMUX_VERSION=$(tmux -V | awk '{print $2}')
        echo "✓ tmux:           ${TMUX_VERSION}"
    else
        echo "✗ tmux:           Not found"
    fi
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  Available Commands:"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
    echo "  GUI              - Launch graphical user interface"
    echo "  simulator        - Run TI simulations"
    echo "  analyzer         - Analyze simulation results"
    echo "  pre-process      - Preprocess MRI data"
    echo "  movea            - MOVEA optimization"
    echo "  ex-search        - Exhaustive search"
    echo "  flex-search      - Flexible search"
    echo "  group_analyzer   - Group analysis"
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
}

# Make CLI scripts executable
chmod +x /ti-toolbox/tit/cli/*.sh

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
    echo "export PATH=\"\$PATH:/ti-toolbox/tit/cli\""
    echo "alias GUI='GUI.sh'"
    echo "alias analyzer='analyzer.sh'"
    echo "alias ex-search='ex-search.sh'"
    echo "alias flex-search='flex-search.sh'"
    echo "alias group_analyzer='group_analyzer.sh'"
    echo "alias movea='movea.sh'"
    echo "alias pre-process='pre-process.sh'"
    echo "alias simulator='simulator.sh'"
    echo ""
    echo "# Display software info on interactive shell"
    echo "if [[ \$- == *i* ]] && [ -z \"\$TI_INFO_SHOWN\" ]; then"
    echo "    export TI_INFO_SHOWN=1"
    echo "    source /usr/local/bin/entrypoint.sh print_info_only"
    echo "fi"
} >> ~/.bashrc

# Setup XDG runtime directory
export XDG_RUNTIME_DIR=/tmp/runtime-root
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# ============================================================================
# Container-side initialization - minimal setup only
# ============================================================================
# Note: Project initialization now handled by loader.sh before container starts

# Handle special case when sourced from .bashrc to display info
if [ "$1" = "print_info_only" ]; then
    print_software_info
    return 0 2>/dev/null || exit 0
fi

# Start interactive shell if no command provided
if [ $# -eq 0 ]; then
    exec /bin/bash
else
    exec "$@"
fi
