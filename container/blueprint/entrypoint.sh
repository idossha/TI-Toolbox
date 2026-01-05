#!/bin/bash
set -euo pipefail

# Initialize .bashrc if it doesn't exist
touch ~/.bashrc

# Source environment setup scripts
if [ -n "${FREESURFER_HOME:-}" ] && [ -f "${FREESURFER_HOME}/SetUpFreeSurfer.sh" ]; then
    # shellcheck source=/dev/null
    source "${FREESURFER_HOME}/SetUpFreeSurfer.sh"
fi

#
# NOTE:
# - CLI entrypoints are defined in `pyproject.toml` and installed at image build
#   time (non-editable).
# - For development, users may mount the repo at /ti-toolbox. We prefer that
#   mounted source to take precedence over the installed package without needing
#   a runtime `pip install -e`.
if [ -d "/ti-toolbox/tit" ]; then
    export PYTHONPATH="/ti-toolbox${PYTHONPATH:+:${PYTHONPATH}}"
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
    
    # Prefer explicit image-tag version (env), fall back to python package version.
    local TI_VERSION="${TI_TOOLBOX_VERSION:-unknown}"
    if command -v simnibs_python >/dev/null 2>&1; then
        local TIT_VERSION
        TIT_VERSION="$(simnibs_python -c "import tit; print(getattr(tit, '__version__', 'unknown'))" 2>/dev/null || true)"
        if { [ "${TI_VERSION}" = "unknown" ] || [ -z "${TI_VERSION}" ]; } && [ -n "${TIT_VERSION}" ] && [ "${TIT_VERSION}" != "unknown" ]; then
            TI_VERSION="v${TIT_VERSION}"
        fi
    fi
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
    echo "  gui              - Launch graphical user interface"
    echo "  simulator        - Run TI simulations"
    echo "  analyzer         - Analyze simulation results"
    echo "  pre_process      - Preprocess MRI data"
    echo "  ex_search        - Exhaustive search"
    echo "  flex_search      - Flexible search"
    echo "  group_analyzer   - Group analysis"
    echo "  create_leadfield - Create leadfields"
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
}

# Display software info on interactive shell once per session
if [[ $- == *i* ]] && [ -z "${TI_INFO_SHOWN:-}" ]; then
    export TI_INFO_SHOWN=1
    print_software_info
fi

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
