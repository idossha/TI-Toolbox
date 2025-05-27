import subprocess
import time
import re
from PyQt6.QtCore import QThread, pyqtSignal


class DockerWorkerThread(QThread):
    """Worker thread for running Docker commands without blocking UI"""
    
    # Signals
    log_signal = pyqtSignal(str, str)  # message, level
    progress_signal = pyqtSignal(str, str, int)  # layer_id, status, percentage
    finished_signal = pyqtSignal(bool, str)  # success, error_message
    
    def __init__(self, cmd, env, script_dir):
        super().__init__()
        self.cmd = cmd
        self.env = env
        self.script_dir = script_dir
        self.should_stop = False
        self.process = None
    
    def stop(self):
        """Stop the worker thread"""
        self.should_stop = True
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass
    
    def run(self):
        """Run the Docker command in the background thread"""
        try:
            self.process = subprocess.Popen(
                self.cmd, 
                cwd=self.script_dir, 
                env=self.env,
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Track state
            shown_images = set()
            shown_containers = set()
            layer_progress = {}  # Track layer download progress
            
            # Read output line by line
            while not self.should_stop and self.process.poll() is None:
                try:
                    output = self.process.stdout.readline()
                    if not output:
                        time.sleep(0.1)
                        continue
                        
                    line = output.strip()
                    if line:
                        self._process_line(line, shown_images, shown_containers, layer_progress)
                        
                except Exception as e:
                    self.log_signal.emit(f"Error reading output: {e}", "WARNING")
                    break
            
            # Wait for process to complete
            if not self.should_stop:
                return_code = self.process.wait()
                success = return_code == 0
                error_msg = "" if success else f"Command failed with exit code {return_code}"
                self.finished_signal.emit(success, error_msg)
            else:
                self.finished_signal.emit(False, "Operation cancelled by user")
                
        except Exception as e:
            self.finished_signal.emit(False, f"Command error: {str(e)}")
    
    def _process_line(self, line, shown_images, shown_containers, layer_progress):
        """Process a single line of Docker output"""
        
        # Handle image pulling with progress
        if "Pulling" in line:
            if " Pulling " in line and "fs layer" not in line.lower():
                image_name = line.split(" ")[0] if " " in line else line
                if image_name not in shown_images:
                    self.log_signal.emit(f"⬇️  Pulling {image_name} image...", "INFO")
                    shown_images.add(image_name)
            elif " Pulled" in line:
                image_name = line.split(" ")[0] if " " in line else line
                self.log_signal.emit(f"✅ {image_name} image ready", "SUCCESS")
            return
        
        # Handle downloading progress with native-style progress bars
        if "Downloading" in line and "[" in line and "]" in line:
            self._handle_download_progress(line, layer_progress)
            return
        
        # Handle Pull complete
        if "Pull complete" in line:
            layer_id = line.split()[0] if line.split() else ""
            if layer_id in layer_progress:
                self.progress_signal.emit(layer_id, "✅ Complete", 100)
                del layer_progress[layer_id]
            return
        
        # Skip already exists messages
        if "Already exists" in line:
            return
        
        # Handle container operations
        if "Container" in line:
            if "Creating" in line:
                container_name = self._extract_container_name(line)
                if container_name and container_name not in shown_containers:
                    self.log_signal.emit(f"📦 Creating container: {container_name}", "INFO")
                    shown_containers.add(container_name)
            elif "Starting" in line:
                container_name = self._extract_container_name(line)
                if container_name:
                    self.log_signal.emit(f"🚀 Starting container: {container_name}", "INFO")
            elif "Started" in line:
                container_name = self._extract_container_name(line)
                if container_name:
                    self.log_signal.emit(f"✅ Container ready: {container_name}", "SUCCESS")
            return
        
        # Handle network operations
        if "Network" in line:
            if "Creating" in line:
                self.log_signal.emit("🌐 Setting up Docker network...", "INFO")
            elif "Created" in line:
                self.log_signal.emit("✅ Network ready", "SUCCESS")
            return
        
        # Handle errors and warnings
        if any(keyword in line.lower() for keyword in ["error", "failed", "denied"]):
            self.log_signal.emit(line, "ERROR")
        elif any(keyword in line.lower() for keyword in ["warning", "warn"]):
            self.log_signal.emit(line, "WARNING")
        elif line.strip() and not self._is_noise(line):
            self.log_signal.emit(line, "INFO")
    
    def _handle_download_progress(self, line, layer_progress):
        """Handle download progress lines and emit progress signals"""
        try:
            # Parse line like: "a1b2c3d4e5f6 Downloading [====>    ] 12.3MB/45.6MB"
            parts = line.split()
            if len(parts) < 3:
                return
                
            layer_id = parts[0]
            
            # Extract progress bar
            progress_match = re.search(r'\[([=>\s]*)\]', line)
            if not progress_match:
                return
                
            progress_bar = progress_match.group(1)
            
            # Calculate percentage from progress bar
            total_chars = len(progress_bar)
            if total_chars > 0:
                filled_chars = progress_bar.count('=') + progress_bar.count('>')
                percentage = int((filled_chars / total_chars) * 100)
            else:
                percentage = 0
            
            # Extract size info if available
            size_match = re.search(r'(\d+(?:\.\d+)?[KMGT]?B)/(\d+(?:\.\d+)?[KMGT]?B)', line)
            if size_match:
                current_size = size_match.group(1)
                total_size = size_match.group(2)
                status = f"📥 {current_size}/{total_size}"
            else:
                status = "📥 Downloading..."
            
            # Only emit if this is a new layer or progress changed significantly
            if (layer_id not in layer_progress or 
                abs(layer_progress[layer_id] - percentage) >= 5):
                
                self.progress_signal.emit(layer_id, status, percentage)
                layer_progress[layer_id] = percentage
                
        except Exception:
            # If parsing fails, just continue
            pass
    
    def _extract_container_name(self, line):
        """Extract container name from Docker output"""
        try:
            if "Container " in line:
                return line.split("Container ")[1].split(" ")[0]
        except:
            pass
        return ""
    
    def _is_noise(self, line):
        """Check if line is noise that should be filtered out"""
        noise_patterns = [
            "Digest:",
            "Status:",
            "Image is up to date",
            "Using default tag:",
        ]
        return any(pattern in line for pattern in noise_patterns) 