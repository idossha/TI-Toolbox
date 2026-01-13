# GPU Acceleration for TI-Toolbox Ex-Search

## Overview

TI-Toolbox includes integrated GPU acceleration support for the Exhaustive Search (`opt.ex`) algorithm using NVIDIA CUDA. GPU acceleration can significantly speed up electric field simulations and TI envelope calculations when testing large numbers of electrode montages.

**Key Feature**: GPU support is **built-in** to the standard Docker image. No separate builds required. It automatically detects and uses NVIDIA GPUs when available, or falls back to CPU when not.

### What is Accelerated?

The following computations are GPU-accelerated when enabled:

1. **Electric Field Calculations**: Matrix-vector operations using leadfield matrices
2. **TI Envelope Computation**: Element-wise array operations for modulation envelope
3. **ROI Metrics Calculation**: Statistical aggregations (mean, max, focality)

**Expected speedup**: 2-10x faster compared to CPU, depending on problem size and GPU hardware.

---

## Default Behavior: Automatic CPU/GPU Detection

- **By default, CPU mode is used** (`USE_GPU=0`)
- GPU libraries (CuPy) are always installed in the Docker image
- If you have NVIDIA GPU + nvidia-docker2 + set `USE_GPU=1`, GPU is automatically used
- If GPU unavailable or `USE_GPU=0`, everything runs on CPU (no errors, automatic fallback)

**No separate builds. No redundancy. One unified image.**

---

## Requirements for GPU Usage

### Hardware
- NVIDIA GPU with CUDA Compute Capability 6.0+ (GTX 1060 or newer)
- At least 8GB VRAM (16GB+ recommended for large problems)

### Software
- Linux (Ubuntu 20.04+) or Windows 10/11 with WSL2
- NVIDIA drivers ≥525.x
- Docker 20.10+
- `nvidia-docker2` package

### Not Supported
- AMD GPUs (no ROCm support yet)
- Apple Silicon / macOS (Docker on Mac runs Linux containers without GPU access)
- Intel integrated GPUs

---

## Installation

### Step 1: Verify NVIDIA GPU and Drivers

```bash
nvidia-smi
```

You should see your GPU listed with driver version ≥525.x.

### Step 2: Install nvidia-docker2

#### Ubuntu/Debian:

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

#### Windows WSL2:

1. Install WSL2 with Ubuntu distribution
2. Install NVIDIA drivers for WSL2 (from NVIDIA website)
3. Inside WSL2 Ubuntu, run the commands above

### Step 3: Test GPU Access from Docker

```bash
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
```

You should see your GPU information. If this fails, troubleshoot nvidia-docker2 before proceeding.

### Step 4: Build TI-Toolbox Image

Build the standard image (GPU support is always included):

```bash
cd /path/to/TI-Toolbox

docker build --platform linux/amd64 \
    -f container/blueprint/Dockerfile.simnibs \
    -t idossha/simnibs:v2.2.3 .
```

**Note**: CuPy (CUDA library) is automatically installed during build. No special flags needed.

### Step 5: Verify GPU Support

```bash
# Test NVIDIA runtime access
docker run --rm --gpus all idossha/simnibs:v2.2.3 nvidia-smi

# Test CuPy is installed
docker run --rm --gpus all idossha/simnibs:v2.2.3 \
    simnibs_python -c "import cupy; print(f'GPU: {cupy.cuda.Device().name}')"

# Test TI-Toolbox GPU module
docker run --rm --gpus all idossha/simnibs:v2.2.3 \
    simnibs_python -c "from tit.opt.ex.gpu_acceleration import get_gpu_info; import json; print(json.dumps(get_gpu_info(), indent=2))"
```

---

## Usage

### Method 1: Docker Run (Quick Testing)

#### Without GPU (default):
```bash
docker run -it --rm \
    -e PROJECT_DIR_NAME="my_project" \
    -v "/path/to/project:/mnt/my_project" \
    idossha/simnibs:v2.2.3 bash
```

#### With GPU:
```bash
docker run -it --rm \
    --gpus all \
    -e USE_GPU=1 \
    -e PROJECT_DIR_NAME="my_project" \
    -v "/path/to/project:/mnt/my_project" \
    idossha/simnibs:v2.2.3 bash
```

Inside container:
```bash
cd /mnt/my_project
bash code/tit/cli/ex-search.sh
```

### Method 2: Docker Compose (Recommended)

#### Step 1: Edit docker-compose.yml

If you have NVIDIA GPU, uncomment the GPU support section in `docker-compose.yml`:

```yaml
simnibs:
  # ... existing configuration ...

  # GPU Support (NVIDIA CUDA only) - Uncomment the 6 lines below if you have NVIDIA GPU
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

#### Step 2: Set Environment Variables

Create or edit `.env` file:

```bash
LOCAL_PROJECT_DIR=/path/to/your/project
PROJECT_DIR_NAME=my_project
DISPLAY=:0
TZ=America/Chicago
USE_GPU=1  # Set to 1 for GPU, 0 for CPU
```

#### Step 3: Start Container

```bash
docker compose up -d
docker compose exec simnibs bash
```

Inside container:
```bash
cd /mnt/${PROJECT_DIR_NAME}
bash code/tit/cli/ex-search.sh
```

### Method 3: Runtime Toggle

You can switch between CPU and GPU without rebuilding or restarting:

```bash
# Enable GPU
export USE_GPU=1
bash code/tit/cli/ex-search.sh

# Disable GPU (use CPU)
export USE_GPU=0
bash code/tit/cli/ex-search.sh
```

---

## Verification

### Check GPU Status at Startup

The ex-search log will show GPU status:

**GPU Enabled:**
```
================================================================================
GPU Acceleration ENABLED
================================================================================
Backend: CUDA
Device: NVIDIA GeForce RTX 4090
Memory: 24.00 GB total, 23.85 GB free
Compute Capability: 8.9
================================================================================
```

**GPU Disabled:**
```
GPU Acceleration DISABLED - Using CPU
```

**GPU Unavailable (fallback to CPU):**
```
================================================================================
GPU requested but not available - falling back to CPU
================================================================================
To enable GPU acceleration:
  1. Run container with: --gpus all
  2. Install nvidia-docker2 on host
  3. Set environment: USE_GPU=1
================================================================================
```

### Monitor GPU During Execution

```bash
# Watch GPU usage in real-time
watch -n 1 nvidia-smi

# Or from another terminal
docker exec simnibs_container nvidia-smi
```

Expected during ex-search:
- **GPU Utilization**: 80-100%
- **Memory Usage**: Increases with leadfield size
- **Temperature**: <85°C (ensure good cooling)

---

## Performance

### Expected Speedups

| Problem Size | Montages | CPU Time | GPU Time | Speedup |
|--------------|----------|----------|----------|---------|
| Small        | 500      | 5 min    | 3 min    | 1.7x    |
| Medium       | 2,000    | 20 min   | 5 min    | 4.0x    |
| Large        | 10,000   | 100 min  | 15 min   | 6.7x    |
| Very Large   | 50,000   | 500 min  | 60 min   | 8.3x    |

*Actual performance depends on GPU model, leadfield size, and system configuration.*

### When to Use GPU vs CPU

**Use GPU when:**
- Testing >1000 montage combinations
- Large leadfield matrices (>10,000 elements)
- GPU has ≥12GB VRAM
- You have modern NVIDIA GPU (RTX series)

**Use CPU when:**
- Testing <500 montages (overhead not worth it)
- Limited VRAM (<8GB)
- No NVIDIA GPU available
- Small problems where CPU is competitive

---

## Troubleshooting

### Issue 1: "GPU requested but not available"

**Cause**: CuPy can't detect NVIDIA GPU

**Solutions**:
1. Check `nvidia-smi` works on host
2. Run container with `--gpus all` flag
3. Verify nvidia-docker2 installed: `docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi`
4. Check Docker daemon config: `cat /etc/docker/daemon.json` (should contain nvidia runtime)
5. Restart Docker: `sudo systemctl restart docker`

### Issue 2: Out of Memory Error

**Symptoms**: `cupy.cuda.memory.OutOfMemoryError`

**Solutions**:
1. Monitor VRAM: `nvidia-smi`
2. Reduce ROI radius or electrode count
3. Close other GPU applications
4. Upgrade to GPU with more VRAM
5. Use CPU: `USE_GPU=0`

### Issue 3: Slower with GPU than CPU

**Causes**:
- Problem too small (transfer overhead dominates)
- GPU thermal throttling
- Old GPU with low compute capability

**Solutions**:
1. Check GPU utilization: `nvidia-smi dmon` (should be >80%)
2. Check temperature (should be <85°C)
3. Use CPU for small problems (<500 montages)

### Issue 4: Docker Compose Fails to Start

**Symptoms**: Error about nvidia runtime when starting compose

**Cause**: GPU deploy section uncommented but nvidia-docker2 not installed

**Solutions**:
- Install nvidia-docker2 (see installation section)
- OR comment out the deploy section in docker-compose.yml
- Container will still work on CPU if deploy section is commented

---

## Technical Details

### Architecture

- **Module**: `tit/opt/ex/gpu_acceleration.py`
- **Backend**: CuPy (CUDA 12.x)
- **Detection**: Automatic at runtime
- **Fallback**: Graceful to CPU via SimNIBS

### GPU Operations

Accelerated functions:
- `get_field_gpu()`: Electric field from leadfield
- `get_maxTI_gpu()`: TI modulation envelope
- `calculate_roi_metrics_gpu()`: ROI statistics

### Memory Management

- Leadfield transferred to GPU per montage
- Results computed on GPU, returned to CPU
- Automatic memory cleanup after each calculation

---

## FAQ

**Q: Do I need to rebuild the image for GPU support?**
A: No. GPU support is built into the standard image. Just use `--gpus all` and `USE_GPU=1`.

**Q: Will it work without NVIDIA GPU?**
A: Yes. It automatically falls back to CPU. No errors, no special configuration needed.

**Q: Can I switch between CPU and GPU without restarting?**
A: Yes. Just change `USE_GPU` environment variable between runs.

**Q: Does this affect CPU-only users?**
A: No. CuPy is installed but not imported unless GPU is requested. Zero impact on CPU users.

**Q: What about AMD GPUs?**
A: Not supported yet. Only NVIDIA CUDA is supported currently.

**Q: Does GPU work on macOS?**
A: No. Docker on macOS runs Linux containers that cannot access GPU hardware.

**Q: Is accuracy affected by GPU?**
A: No. Results are numerically identical to CPU within floating-point precision.

**Q: How much VRAM do I need?**
A: Minimum 8GB, 16GB+ recommended for large problems.

---

## Quick Reference

### Build Image
```bash
docker build --platform linux/amd64 \
  -f container/blueprint/Dockerfile.simnibs \
  -t idossha/simnibs:v2.2.3 .
```

### Test GPU
```bash
docker run --rm --gpus all idossha/simnibs:v2.2.3 nvidia-smi
```

### Run with GPU
```bash
docker run -it --rm --gpus all -e USE_GPU=1 \
  -v "/path/to/project:/mnt/project" \
  idossha/simnibs:v2.2.3 bash
```

### Monitor GPU
```bash
watch -n 1 nvidia-smi
```

---

## Support

**Issues**: https://github.com/idossha/TI-Toolbox/issues
**Maintainer**: Ido Haber (ihaber@wisc.edu)

When reporting GPU issues, include:
- GPU model and VRAM
- Output of `nvidia-smi`
- Output of `get_gpu_info()` from container
- Full error log

---

**Last Updated**: 2026-01-12
