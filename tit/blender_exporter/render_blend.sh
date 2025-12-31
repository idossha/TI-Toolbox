#!/usr/bin/env bash
set -e

# --------------------------------------------------
# Usage:
#   ./render_blend.sh your_file.blend [output_dir]
# --------------------------------------------------

BLEND_FILE="$1"
OUTPUT_DIR="${2:-renders}"

if [[ -z "$BLEND_FILE" ]]; then
  echo "Usage: $0 your_file.blend [output_dir]"
  exit 1
fi

# --------------------------------------------------
# Find Blender executable (cross-OS)
# --------------------------------------------------
find_blender() {
  # 1. PATH
  if command -v blender >/dev/null 2>&1; then
    command -v blender
    return
  fi

  # 2. macOS
  if [[ "$OSTYPE" == "darwin"* ]]; then
    local mac="/Applications/Blender.app/Contents/MacOS/Blender"
    [[ -x "$mac" ]] && echo "$mac" && return
  fi

  # 3. Linux
  for p in /usr/bin/blender /usr/local/bin/blender /snap/bin/blender; do
    [[ -x "$p" ]] && echo "$p" && return
  done

  # 4. Windows (Git Bash / MSYS / WSL)
  for p in \
    "/c/Program Files/Blender Foundation/Blender/blender.exe" \
    "/c/Program Files (x86)/Blender Foundation/Blender/blender.exe"; do
    [[ -x "$p" ]] && echo "$p" && return
  done

  return 1
}

BLENDER_BIN="$(find_blender)" || {
  echo "ERROR: Blender executable not found"
  exit 1
}

echo "Using Blender: $BLENDER_BIN"

# --------------------------------------------------
# Create temporary Python script (Blender 4.x safe)
# --------------------------------------------------
PY_SCRIPT="$(mktemp /tmp/blender_render_XXXX.py)"

cat > "$PY_SCRIPT" <<'PYEOF'
import bpy
import os

scene = bpy.context.scene

# ---- Force a valid render engine (Blender 4.x)
try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    print("Using Eevee Next")
except:
    scene.render.engine = 'CYCLES'
    print("Falling back to Cycles")

# ---- Output directory
blend_dir = os.path.dirname(bpy.data.filepath)
output_dir = os.path.join(blend_dir, os.environ.get("OUTPUT_DIR", "renders"))
os.makedirs(output_dir, exist_ok=True)

# ---- Collect cameras
cameras = [obj for obj in bpy.data.objects if obj.type == 'CAMERA']

if not cameras:
    raise RuntimeError("No cameras found in the scene")

# ---- Render each camera
for cam in cameras:
    scene.camera = cam
    scene.render.filepath = os.path.join(output_dir, cam.name)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered camera: {cam.name}")
PYEOF

export OUTPUT_DIR="$OUTPUT_DIR"

# --------------------------------------------------
# Run Blender
# --------------------------------------------------
"$BLENDER_BIN" -b "$BLEND_FILE" -P "$PY_SCRIPT"

# --------------------------------------------------
# Cleanup
# --------------------------------------------------
rm -f "$PY_SCRIPT"
