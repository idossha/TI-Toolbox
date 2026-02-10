#!/usr/bin/env bash
# ============================================================================
# apptainer_run.sh - HPC wrapper for TI-Toolbox Apptainer/Singularity images
# ============================================================================
#
# Usage:
#   ./apptainer_run.sh --sif ti-toolbox.sif --project-dir /scratch/myproject
#   ./apptainer_run.sh --sif ti-toolbox.sif --mode exec --cmd "simulator --help"
#   ./apptainer_run.sh --sif ti-toolbox.sif --mode slurm-template
#
# See --help for all options.
# ============================================================================

set -euo pipefail

# ============================================================================
# Defaults
# ============================================================================
SIF=""
PROJECT_DIR=""
FS_LICENSE=""
SCRATCH=""
MODE="interactive"
CMD=""
GPUS=""
EXTRA_BINDS=()
RUNTIME=""

# ============================================================================
# Color helpers (disabled if not a terminal)
# ============================================================================
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' NC=''
fi

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { error "$@"; exit 1; }

# ============================================================================
# Usage
# ============================================================================
usage() {
    cat <<EOF
${BOLD}TI-Toolbox Apptainer/Singularity Launcher${NC}

${BOLD}USAGE:${NC}
    $(basename "$0") [OPTIONS]

${BOLD}REQUIRED:${NC}
    --sif PATH              Path to the .sif image file

${BOLD}OPTIONS:${NC}
    --project-dir PATH      Project directory to bind-mount at /mnt/<basename>
    --fs-license PATH       FreeSurfer license.txt (auto-detected if not set)
    --scratch PATH          Scratch directory to bind at /scratch
    --mode MODE             Run mode: interactive (default), exec, slurm-template
    --cmd COMMAND           Command to run in exec mode
    --gpus                  Enable GPU passthrough (--nv flag)
    --extra-bind SRC:DST    Additional bind mount (can be repeated)
    -h, --help              Show this help message

${BOLD}MODES:${NC}
    interactive     Launch an interactive shell inside the container (default)
    exec            Execute a specific command (requires --cmd)
    slurm-template  Print a SLURM job script template to stdout

${BOLD}FREESURFER LICENSE AUTO-DETECTION:${NC}
    The script searches these locations in order:
      1. --fs-license argument
      2. \$FS_LICENSE environment variable
      3. \$FREESURFER_HOME/license.txt
      4. ~/.freesurfer/license.txt

${BOLD}EXAMPLES:${NC}
    # Interactive session
    $(basename "$0") --sif ti-toolbox.sif --project-dir /data/study01

    # Run a simulation
    $(basename "$0") --sif ti-toolbox.sif --project-dir /data/study01 \\
        --mode exec --cmd "simnibs_python -m tit.cli.simulator --help"

    # Generate a SLURM script
    $(basename "$0") --sif ti-toolbox.sif --project-dir /data/study01 \\
        --mode slurm-template > submit.sh

    # With GPU support
    $(basename "$0") --sif ti-toolbox.sif --project-dir /data/study01 --gpus

EOF
    exit 0
}

# ============================================================================
# Argument parsing
# ============================================================================
parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --sif)          SIF="$2";         shift 2 ;;
            --project-dir)  PROJECT_DIR="$2"; shift 2 ;;
            --fs-license)   FS_LICENSE="$2";  shift 2 ;;
            --scratch)      SCRATCH="$2";     shift 2 ;;
            --mode)         MODE="$2";        shift 2 ;;
            --cmd)          CMD="$2";         shift 2 ;;
            --gpus)         GPUS="yes";       shift   ;;
            --extra-bind)   EXTRA_BINDS+=("$2"); shift 2 ;;
            -h|--help)      usage ;;
            *)              die "Unknown option: $1. Use --help for usage." ;;
        esac
    done
}

# ============================================================================
# Detect container runtime (apptainer or singularity)
# ============================================================================
detect_runtime() {
    if command -v apptainer >/dev/null 2>&1; then
        RUNTIME="apptainer"
    elif command -v singularity >/dev/null 2>&1; then
        RUNTIME="singularity"
    else
        die "Neither 'apptainer' nor 'singularity' found in PATH.\n" \
            "  Install Apptainer: https://apptainer.org/docs/admin/main/installation.html"
    fi
    info "Using runtime: $RUNTIME ($(command -v $RUNTIME))"
}

# ============================================================================
# Validate inputs
# ============================================================================
validate() {
    # SIF is always required (except slurm-template can work without it)
    if [ -z "$SIF" ] && [ "$MODE" != "slurm-template" ]; then
        die "Missing required --sif argument. Use --help for usage."
    fi

    if [ -n "$SIF" ] && [ ! -f "$SIF" ]; then
        die "SIF image not found: $SIF"
    fi

    if [ -n "$PROJECT_DIR" ] && [ ! -d "$PROJECT_DIR" ]; then
        die "Project directory not found: $PROJECT_DIR"
    fi

    if [ "$MODE" = "exec" ] && [ -z "$CMD" ]; then
        die "Mode 'exec' requires --cmd argument."
    fi

    case "$MODE" in
        interactive|exec|slurm-template) ;;
        *) die "Invalid mode: $MODE (must be interactive, exec, or slurm-template)" ;;
    esac
}

# ============================================================================
# Auto-detect FreeSurfer license
# ============================================================================
find_fs_license() {
    if [ -n "$FS_LICENSE" ]; then
        if [ ! -f "$FS_LICENSE" ]; then
            die "FreeSurfer license not found at: $FS_LICENSE"
        fi
        info "FreeSurfer license: $FS_LICENSE (from --fs-license)"
        return
    fi

    # Check environment variable
    if [ -n "${FS_LICENSE:-}" ] && [ -f "${FS_LICENSE}" ]; then
        info "FreeSurfer license: $FS_LICENSE (from \$FS_LICENSE)"
        return
    fi

    # Check FREESURFER_HOME
    if [ -n "${FREESURFER_HOME:-}" ] && [ -f "${FREESURFER_HOME}/license.txt" ]; then
        FS_LICENSE="${FREESURFER_HOME}/license.txt"
        info "FreeSurfer license: $FS_LICENSE (from \$FREESURFER_HOME)"
        return
    fi

    # Check home directory
    if [ -f "$HOME/.freesurfer/license.txt" ]; then
        FS_LICENSE="$HOME/.freesurfer/license.txt"
        info "FreeSurfer license: $FS_LICENSE (from ~/.freesurfer/)"
        return
    fi

    warn "FreeSurfer license not found. FreeSurfer commands will fail."
    warn "  Set --fs-license, \$FS_LICENSE, or place at ~/.freesurfer/license.txt"
}

# ============================================================================
# Assemble bind mounts
# ============================================================================
assemble_binds() {
    BIND_ARGS=()

    # Project directory
    if [ -n "$PROJECT_DIR" ]; then
        local basename
        basename=$(basename "$PROJECT_DIR")
        BIND_ARGS+=(--bind "${PROJECT_DIR}:/mnt/${basename}")
        info "Binding project: ${PROJECT_DIR} -> /mnt/${basename}"
    fi

    # FreeSurfer license (read-only)
    if [ -n "$FS_LICENSE" ]; then
        BIND_ARGS+=(--bind "${FS_LICENSE}:/usr/local/freesurfer/license.txt:ro")
        info "Binding FS license (read-only)"
    fi

    # Scratch directory
    if [ -n "$SCRATCH" ]; then
        if [ ! -d "$SCRATCH" ]; then
            die "Scratch directory not found: $SCRATCH"
        fi
        BIND_ARGS+=(--bind "${SCRATCH}:/scratch")
        info "Binding scratch: ${SCRATCH} -> /scratch"
    fi

    # Extra user-specified binds
    for bind in "${EXTRA_BINDS[@]}"; do
        BIND_ARGS+=(--bind "$bind")
        info "Binding extra: $bind"
    done
}

# ============================================================================
# Print version banner
# ============================================================================
print_banner() {
    echo ""
    echo -e "${BOLD}================================================================${NC}"
    echo -e "${BOLD}  TI-Toolbox - HPC Launcher${NC}"
    echo -e "${BOLD}================================================================${NC}"
    echo ""
    echo -e "  Runtime:    ${CYAN}${RUNTIME}${NC}"
    echo -e "  Image:      ${CYAN}${SIF}${NC}"
    if [ -n "$PROJECT_DIR" ]; then
        echo -e "  Project:    ${CYAN}${PROJECT_DIR}${NC}"
    fi
    if [ -n "$FS_LICENSE" ]; then
        echo -e "  FS License: ${CYAN}${FS_LICENSE}${NC}"
    fi
    if [ -n "$GPUS" ]; then
        echo -e "  GPU:        ${CYAN}enabled${NC}"
    fi
    echo ""
}

# ============================================================================
# Run modes
# ============================================================================
run_interactive() {
    print_banner
    info "Starting interactive session..."
    echo ""

    local gpu_flag=""
    [ -n "$GPUS" ] && gpu_flag="--nv"

    $RUNTIME run \
        ${gpu_flag} \
        "${BIND_ARGS[@]}" \
        "$SIF"
}

run_exec() {
    print_banner
    info "Executing: $CMD"
    echo ""

    local gpu_flag=""
    [ -n "$GPUS" ] && gpu_flag="--nv"

    $RUNTIME exec \
        ${gpu_flag} \
        "${BIND_ARGS[@]}" \
        "$SIF" \
        bash -c "$CMD"
}

print_slurm_template() {
    local sif_path="${SIF:-/path/to/ti-toolbox.sif}"
    local project_path="${PROJECT_DIR:-/path/to/project}"
    local project_base
    project_base=$(basename "${project_path}")
    local license_path="${FS_LICENSE:-/path/to/license.txt}"

    cat <<SLURM
#!/bin/bash
#SBATCH --job-name=ti-toolbox
#SBATCH --output=ti-toolbox_%j.out
#SBATCH --error=ti-toolbox_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
# #SBATCH --partition=gpu
# #SBATCH --gres=gpu:1

# ============================================================================
# TI-Toolbox SLURM Job Script
# Generated by apptainer_run.sh on $(date +%Y-%m-%d)
# ============================================================================

# Load apptainer module (adjust for your cluster)
# module load apptainer

SIF="${sif_path}"
PROJECT_DIR="${project_path}"
FS_LICENSE="${license_path}"

echo "Job \${SLURM_JOB_ID} starting on \$(hostname) at \$(date)"
echo "CPUs: \${SLURM_CPUS_PER_TASK}, Memory: \${SLURM_MEM_PER_NODE}MB"

apptainer exec \\
    --bind "\${PROJECT_DIR}:/mnt/${project_base}" \\
    --bind "\${FS_LICENSE}:/usr/local/freesurfer/license.txt:ro" \\
    "\${SIF}" \\
    simnibs_python -m tit.cli.simulator \\
        --project "/mnt/${project_base}" \\
        --subject sub-001

echo "Job completed at \$(date)"
SLURM
}

# ============================================================================
# Main
# ============================================================================
main() {
    parse_args "$@"

    # slurm-template mode can run without runtime or validation
    if [ "$MODE" = "slurm-template" ]; then
        print_slurm_template
        exit 0
    fi

    detect_runtime
    validate
    find_fs_license
    assemble_binds

    case "$MODE" in
        interactive) run_interactive ;;
        exec)        run_exec ;;
    esac
}

main "$@"
