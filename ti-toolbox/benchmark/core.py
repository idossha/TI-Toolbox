#!/usr/bin/env python3
"""
Benchmarking Tool for TI-Toolbox
Provides timing, hardware profiling, and performance metrics for preprocessing steps.
"""

import time
import json
import platform
import psutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, asdict
import sys


@dataclass
class HardwareInfo:
    """Container for hardware information."""
    # CPU Information
    cpu_model: str
    cpu_physical_cores: int
    cpu_logical_cores: int
    cpu_freq_max: float
    cpu_freq_min: float
    cpu_freq_current: float
    
    # Memory Information
    total_memory_gb: float
    available_memory_gb: float
    
    # GPU Information (if available)
    gpu_available: bool
    gpu_devices: List[Dict[str, Any]]
    
    # System Information
    platform: str
    platform_version: str
    python_version: str
    
    # Timestamp
    timestamp: str


@dataclass
class BenchmarkResult:
    """Container for benchmark results."""
    process_name: str
    start_time: str
    end_time: str
    duration_seconds: float
    duration_formatted: str
    
    # Resource usage
    peak_memory_mb: float
    avg_cpu_percent: float
    
    # Hardware context
    hardware_info: HardwareInfo
    
    # Additional metadata
    metadata: Dict[str, Any]
    
    # Status
    success: bool
    error_message: Optional[str] = None


class BenchmarkTimer:
    """Timer utility for benchmarking processes."""
    
    def __init__(self, process_name: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize the benchmark timer.
        
        Args:
            process_name: Name of the process being benchmarked
            metadata: Additional metadata to store with the benchmark
        """
        self.process_name = process_name
        self.metadata = metadata or {}
        self.start_time = None
        self.end_time = None
        self.start_memory = None
        self.peak_memory = 0.0
        self.cpu_samples = []
        self.monitoring = False
        self.current_process = psutil.Process()  # Cache current process
        
    def start(self):
        """Start the benchmark timer."""
        self.start_time = time.time()
        self.start_memory = psutil.Process().memory_info().rss / (1024 * 1024)  # MB
        self.monitoring = True
        print(f"[BENCHMARK] Starting: {self.process_name}")
        print(f"[BENCHMARK] Start time: {datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S')}")
        
    def sample(self):
        """Take a sample of current resource usage including child processes."""
        if not self.monitoring:
            return
            
        try:
            # Sample parent process
            parent_memory = self.current_process.memory_info().rss / (1024 * 1024)  # MB
            parent_cpu = self.current_process.cpu_percent(interval=0.01)
            
            # Sample all child processes (subprocesses like simnibs_python)
            child_memory = 0.0
            child_cpu = 0.0
            try:
                children = self.current_process.children(recursive=True)
                for child in children:
                    try:
                        child_memory += child.memory_info().rss / (1024 * 1024)
                        child_cpu += child.cpu_percent(interval=0.01)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            
            # Total resource usage (parent + children)
            total_memory = parent_memory + child_memory
            total_cpu = parent_cpu + child_cpu
            
            self.peak_memory = max(self.peak_memory, total_memory)
            self.cpu_samples.append(total_cpu)
            
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    def stop(self, success: bool = True, error_message: Optional[str] = None) -> BenchmarkResult:
        """
        Stop the benchmark timer and return results.
        
        Args:
            success: Whether the process completed successfully
            error_message: Optional error message if process failed
            
        Returns:
            BenchmarkResult object containing all benchmark data
        """
        self.end_time = time.time()
        self.monitoring = False
        
        duration = self.end_time - self.start_time
        duration_formatted = self._format_duration(duration)
        
        # Take final sample
        self.sample()
        
        avg_cpu = sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0.0
        
        print(f"[BENCHMARK] Completed: {self.process_name}")
        print(f"[BENCHMARK] Duration: {duration_formatted}")
        print(f"[BENCHMARK] Peak Memory: {self.peak_memory:.2f} MB")
        print(f"[BENCHMARK] Avg CPU: {avg_cpu:.2f}%")
        
        result = BenchmarkResult(
            process_name=self.process_name,
            start_time=datetime.fromtimestamp(self.start_time).isoformat(),
            end_time=datetime.fromtimestamp(self.end_time).isoformat(),
            duration_seconds=duration,
            duration_formatted=duration_formatted,
            peak_memory_mb=self.peak_memory,
            avg_cpu_percent=avg_cpu,
            hardware_info=get_hardware_info(),
            metadata=self.metadata,
            success=success,
            error_message=error_message
        )
        
        return result
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in human-readable format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        success = exc_type is None
        error_message = str(exc_val) if exc_val else None
        self.stop(success=success, error_message=error_message)


def get_hardware_info() -> HardwareInfo:
    """
    Extract comprehensive hardware information.
    
    Returns:
        HardwareInfo object containing system details
    """
    # CPU Information
    cpu_freq = psutil.cpu_freq()
    cpu_model = _get_cpu_model()
    
    # Memory Information
    memory = psutil.virtual_memory()
    
    # GPU Information
    gpu_info = _get_gpu_info()
    
    return HardwareInfo(
        cpu_model=cpu_model,
        cpu_physical_cores=psutil.cpu_count(logical=False),
        cpu_logical_cores=psutil.cpu_count(logical=True),
        cpu_freq_max=cpu_freq.max if cpu_freq else 0.0,
        cpu_freq_min=cpu_freq.min if cpu_freq else 0.0,
        cpu_freq_current=cpu_freq.current if cpu_freq else 0.0,
        total_memory_gb=memory.total / (1024**3),
        available_memory_gb=memory.available / (1024**3),
        gpu_available=gpu_info['available'],
        gpu_devices=gpu_info['devices'],
        platform=platform.system(),
        platform_version=platform.version(),
        python_version=platform.python_version(),
        timestamp=datetime.now().isoformat()
    )


def _get_cpu_model() -> str:
    """Get CPU model name."""
    try:
        if platform.system() == "Darwin":  # macOS
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip()
        elif platform.system() == "Linux":
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[1].strip()
        elif platform.system() == "Windows":
            result = subprocess.run(
                ["wmic", "cpu", "get", "name"],
                capture_output=True,
                text=True,
                timeout=5
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                return lines[1].strip()
    except Exception:
        pass
    
    return "Unknown CPU"


def _get_gpu_info() -> Dict[str, Any]:
    """Get GPU information if available."""
    gpu_info = {
        'available': False,
        'devices': []
    }
    
    # Try NVIDIA GPUs
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            gpu_info['available'] = True
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        gpu_info['devices'].append({
                            'type': 'NVIDIA',
                            'name': parts[0],
                            'memory': parts[1],
                            'driver': parts[2]
                        })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Try AMD GPUs
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            gpu_info['available'] = True
            # Parse AMD GPU info (format may vary)
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if "GPU" in line and ":" in line:
                    gpu_info['devices'].append({
                        'type': 'AMD',
                        'name': line.split(":")[-1].strip(),
                        'memory': 'N/A',
                        'driver': 'N/A'
                    })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Try Metal (macOS)
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.split("\n")
                current_gpu = None
                for line in lines:
                    if "Chipset Model:" in line:
                        current_gpu = line.split(":")[-1].strip()
                    elif "VRAM" in line and current_gpu:
                        vram = line.split(":")[-1].strip()
                        gpu_info['available'] = True
                        gpu_info['devices'].append({
                            'type': 'Metal',
                            'name': current_gpu,
                            'memory': vram,
                            'driver': 'N/A'
                        })
                        current_gpu = None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    
    return gpu_info


def print_hardware_info(hardware_info: Optional[HardwareInfo] = None):
    """
    Print hardware information in a formatted way.
    
    Args:
        hardware_info: HardwareInfo object, if None will fetch current info
    """
    if hardware_info is None:
        hardware_info = get_hardware_info()
    
    print("\n" + "="*70)
    print("HARDWARE INFORMATION")
    print("="*70)
    
    print("\nCPU:")
    print(f"  Model: {hardware_info.cpu_model}")
    print(f"  Physical Cores: {hardware_info.cpu_physical_cores}")
    print(f"  Logical Cores: {hardware_info.cpu_logical_cores}")
    print(f"  Max Frequency: {hardware_info.cpu_freq_max:.2f} MHz")
    print(f"  Current Frequency: {hardware_info.cpu_freq_current:.2f} MHz")
    
    print("\nMemory:")
    print(f"  Total: {hardware_info.total_memory_gb:.2f} GB")
    print(f"  Available: {hardware_info.available_memory_gb:.2f} GB")
    
    print("\nGPU:")
    if hardware_info.gpu_available and hardware_info.gpu_devices:
        for i, gpu in enumerate(hardware_info.gpu_devices):
            print(f"  Device {i}: {gpu['name']} ({gpu['type']})")
            if gpu['memory'] != 'N/A':
                print(f"    Memory: {gpu['memory']}")
            if gpu['driver'] != 'N/A':
                print(f"    Driver: {gpu['driver']}")
    else:
        print("  No GPU detected")
    
    print("\nSystem:")
    print(f"  Platform: {hardware_info.platform} {hardware_info.platform_version}")
    print(f"  Python: {hardware_info.python_version}")
    print(f"  Timestamp: {hardware_info.timestamp}")
    
    print("="*70 + "\n")


def save_benchmark_result(result: BenchmarkResult, output_path: Path):
    """
    Save benchmark result to a JSON file.
    
    Args:
        result: BenchmarkResult object to save
        output_path: Path to save the JSON file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert dataclass to dict
    result_dict = asdict(result)
    
    with open(output_path, 'w') as f:
        json.dump(result_dict, f, indent=2)
    
    print(f"[BENCHMARK] Results saved to: {output_path}")


def load_benchmark_result(input_path: Path) -> BenchmarkResult:
    """
    Load benchmark result from a JSON file.
    
    Args:
        input_path: Path to the JSON file
        
    Returns:
        BenchmarkResult object
    """
    with open(input_path, 'r') as f:
        data = json.load(f)
    
    # Reconstruct nested dataclasses
    data['hardware_info'] = HardwareInfo(**data['hardware_info'])
    return BenchmarkResult(**data)


def print_benchmark_result(result: BenchmarkResult):
    """
    Print benchmark result in a formatted way.
    
    Args:
        result: BenchmarkResult object to print
    """
    print("\n" + "="*70)
    print("BENCHMARK RESULTS")
    print("="*70)
    
    print(f"\nProcess: {result.process_name}")
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    if result.error_message:
        print(f"Error: {result.error_message}")
    
    print(f"\nTiming:")
    print(f"  Start Time: {result.start_time}")
    print(f"  End Time: {result.end_time}")
    print(f"  Duration: {result.duration_formatted} ({result.duration_seconds:.2f}s)")
    
    print(f"\nResource Usage:")
    print(f"  Peak Memory: {result.peak_memory_mb:.2f} MB")
    print(f"  Average CPU: {result.avg_cpu_percent:.2f}%")
    
    if result.metadata:
        print(f"\nMetadata:")
        for key, value in result.metadata.items():
            print(f"  {key}: {value}")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    # Demo usage
    print("TI-Toolbox Benchmarking Tool")
    print_hardware_info()
    
    print("Example usage:")
    print("\nPython API:")
    print("""
    from ti-toolbox.tools.benchmark import BenchmarkTimer
    
    # Using context manager
    with BenchmarkTimer("my_process", metadata={"subject": "ernie"}) as timer:
        # Your code here
        time.sleep(2)
    
    # Manual control
    timer = BenchmarkTimer("my_process")
    timer.start()
    # Your code here
    result = timer.stop()
    print_benchmark_result(result)
    save_benchmark_result(result, "benchmark_results.json")
    """)

