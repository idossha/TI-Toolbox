#!/bin/bash

# TI-Toolbox Project Diagnostic Script
# Prints a summary of the project state for quick troubleshooting

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m' # No Color

# Section header
section() {
  echo -e "\n${BLUE}========== $1 ==========${NC}"
}

# Subsection
subsection() {
  echo -e "${YELLOW}--- $1 ---${NC}"
}

# Get environment variables for mounts
if [[ -z "$PROJECT_DIR_NAME" ]]; then
  echo -e "${RED}PROJECT_DIR_NAME environment variable not set!${NC}"
  exit 1
fi
MOUNTED_PROJECT_DIR="/mnt/$PROJECT_DIR_NAME"

if [[ -z "$DEV_CODEBASE_DIR" ]]; then
  echo -e "${YELLOW}DEV_CODEBASE_DIR environment variable not set. Codebase checks will be skipped.${NC}"
  CODEBASE_ROOT=""
else
  CODEBASE_ROOT="/testing"
fi

# Print project directory
section "Mounted Project Directory (Host Data)"
echo -e "Mounted project root: ${GREEN}$MOUNTED_PROJECT_DIR${NC}"
if [[ ! -d "$MOUNTED_PROJECT_DIR" ]]; then
  echo -e "${RED}Mounted project directory not found!${NC}"
  exit 1
fi

# List subject-like folders (exclude known non-subjects)
cd "$MOUNTED_PROJECT_DIR"
KNOWN=(configs utils logs .git)
ALL_DIRS=( $(ls -1) )
SUBJECTS=()
for d in "${ALL_DIRS[@]}"; do
  skip=false
  for k in "${KNOWN[@]}"; do
    if [[ "$d" == "$k" ]]; then skip=true; break; fi
  done
  if [[ "$skip" == false && -d "$d" ]]; then
    SUBJECTS+=("$d")
  fi
done

if [[ ${#SUBJECTS[@]} -eq 0 ]]; then
  echo -e "${RED}No subject folders detected!${NC}"
else
  echo -e "Detected subject folders:"
  for s in "${SUBJECTS[@]}"; do
    echo -e "  - ${GREEN}$s${NC}"
    # Check for key subfolders
    for sub in anat/raw anat/nifti anat/freesurfer SimNIBS/Simulations SimNIBS/flex-search SimNIBS/ex-search SimNIBS/Analysis; do
      if [[ -d "$s/$sub" ]]; then
        count=$(find "$s/$sub" -type f | wc -l)
        echo -e "      [OK] $sub (${count} files)"
      else
        echo -e "      ${RED}[MISSING] $sub${NC}"
      fi
    done
  done
fi

# Host system info
section "Host System Info"
echo -n "OS: "; uname -a
echo -n "Python: "; python3 --version 2>&1

# Check for system info file
INFO_FILE="$MOUNTED_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info/system_info.txt"
section "Host System Info File (derivatives/ti-toolbox/.ti-toolbox-info/system_info.txt)"
if [[ -f "$INFO_FILE" ]]; then
  echo -e "${GREEN}System info file found at: $INFO_FILE${NC}"
  # Extract and display specific fields
  USER_LINE=$(grep '^User:' "$INFO_FILE" | head -1)
  OS_LINE=$(grep '^OS:' "$INFO_FILE" | head -1 | cut -d':' -f2-)
  DISK_SECTION=$(awk '/^## Disk Space \(project dir\)/{flag=1;next}/^$/{flag=0}flag' "$INFO_FILE")
  DOCKER_VERSION=$(grep '^## Docker Version' -A1 "$INFO_FILE" | tail -1)
  DOCKER_ALLOC=$(awk '/^## Docker Resource Allocation/{flag=1;next}/^$/{flag=0}flag' "$INFO_FILE")
  DISPLAY_LINE=$(grep '^## DISPLAY' -A1 "$INFO_FILE" | tail -1)

  [[ -n "$USER_LINE" ]] && echo -e "${YELLOW}$USER_LINE${NC}" || echo -e "${RED}User info missing${NC}"
  [[ -n "$OS_LINE" ]] && echo -e "${YELLOW}OS:${NC} $OS_LINE" || echo -e "${RED}OS info missing${NC}"
  if [[ -n "$DISK_SECTION" ]]; then
    echo -e "${YELLOW}Disk Space (project dir):${NC}"
    echo "$DISK_SECTION" | sed 's/^/    /'
  else
    echo -e "${RED}Disk space info missing${NC}"
  fi
  [[ -n "$DOCKER_VERSION" ]] && echo -e "${YELLOW}Docker Version:${NC} $DOCKER_VERSION" || echo -e "${RED}Docker version info missing${NC}"
  if [[ -n "$DOCKER_ALLOC" ]]; then
    echo -e "${YELLOW}Docker Resource Allocation:${NC}"
    echo "$DOCKER_ALLOC" | sed 's/^/    /'
  else
    echo -e "${RED}Docker resource allocation info missing${NC}"
  fi
  [[ -n "$DISPLAY_LINE" ]] && echo -e "${YELLOW}DISPLAY:${NC} $DISPLAY_LINE" || echo -e "${RED}DISPLAY info missing${NC}"
else
  echo -e "${YELLOW}System info file not found at $INFO_FILE${NC}"
fi

# Configs (look for *.json under config/ subdir)
section "User Configs ($MOUNTED_PROJECT_DIR/config)"
CONFIG_DIR="$MOUNTED_PROJECT_DIR/config"
CONFIG_FILES=( $(ls "$CONFIG_DIR"/*.json 2>/dev/null || true) )
if [[ ! -d "$CONFIG_DIR" ]]; then
  echo -e "${RED}Config directory $CONFIG_DIR does not exist!${NC}"
elif [[ ${#CONFIG_FILES[@]} -eq 0 ]]; then
  echo -e "${RED}No config .json files found in $CONFIG_DIR!${NC}"
else
  echo -e "Config .json files found:"
  for f in "${CONFIG_FILES[@]}"; do
    if [[ -f "$f" ]]; then
      echo -e "  - ${GREEN}$(basename "$f")${NC}"
    fi
  done
fi

# Utils (look for .json files)
section "Utils ($MOUNTED_PROJECT_DIR/utils)"
for util in roi_list.json montage_list.json; do
  if [[ -f "$MOUNTED_PROJECT_DIR/utils/$util" ]]; then
    echo -e "[OK] utils/$util present"
  else
    echo -e "${YELLOW}[WARN] utils/$util missing${NC}"
  fi
done

# Codebase checks (optional)
if [[ -n "$CODEBASE_ROOT" && -d "$CODEBASE_ROOT" ]]; then
  section "Codebase Root ($CODEBASE_ROOT)"
  echo -e "Codebase root: ${GREEN}$CODEBASE_ROOT${NC}"
  ls -1 "$CODEBASE_ROOT" | sed 's/^/  - /'
fi

# Relevant environment variables
section "Relevant Environment Variables"
env | grep -Ei '^(FSL|FREESURFER|SIMNIBS|PROJECT_DIR|DEV_CODEBASE|SUBJECTS_DIR|FS_LICENSE|FSFAST|MNI|POSSUM|DISPLAY|USER|PATH)=' | while IFS='=' read -r var val; do
  echo -e "${YELLOW}$var${NC}=${GREEN}$val${NC}"
done

# Tool availability check
section "Tool Availability in Docker Environment"
for tool in freesurfer simnibs dcm2niix fsl ; do
  if command -v "$tool" &>/dev/null; then
    echo -e "[OK] $tool"
  else
    echo -e "${RED}[MISSING] $tool${NC}"
  fi
done

echo -e "\n${BLUE}========== END OF DIAGNOSTICS ==========${NC}\n" 