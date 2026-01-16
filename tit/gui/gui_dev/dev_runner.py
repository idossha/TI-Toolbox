#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-
"""
Development runner with auto-reload for TI-Toolbox GUI
Watches for file changes and automatically restarts the GUI
"""

import sys
import os
import time
import subprocess
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Installing watchdog for auto-reload functionality...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler


class GUIReloadHandler(FileSystemEventHandler):
    """Handler for file system events that triggers GUI restart"""
    
    def __init__(self, restart_callback):
        super().__init__()
        self.restart_callback = restart_callback
        self.last_restart = 0
        self.debounce_seconds = 1  # Prevent multiple restarts for rapid saves
    
    def on_modified(self, event):
        """Called when a file is modified"""
        if event.is_directory:
            return
        
        # Only watch Python files
        if not event.src_path.endswith('.py'):
            return
        
        # Debounce: ignore if we just restarted
        current_time = time.time()
        if current_time - self.last_restart < self.debounce_seconds:
            return
        
        print(f"\n🔄 Detected change in: {os.path.basename(event.src_path)}")
        self.last_restart = current_time
        self.restart_callback()


class GUIRunner:
    """Manages the GUI process with auto-restart capability"""
    
    def __init__(self):
        self.process = None
        self.observer = None
        self.gui_dir = Path(__file__).parent
        self.running = True
    
    def start_gui(self):
        """Start the GUI process"""
        if self.process and self.process.poll() is None:
            print("⏹️  Stopping previous instance...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        print("🚀 Starting TI-Toolbox GUI...")
        # Use same Python interpreter, run main.py
        self.process = subprocess.Popen(
            [sys.executable, "../main.py"],
            cwd=self.gui_dir,
            # Keep output visible
            stdout=sys.stdout,
            stderr=sys.stderr
        )
    
    def setup_watcher(self):
        """Set up file system watcher"""
        event_handler = GUIReloadHandler(self.start_gui)
        self.observer = Observer()
        
        # Watch the GUI directory
        self.observer.schedule(event_handler, str(self.gui_dir), recursive=False)
        
        # Also watch parent directory for shared utilities
        parent_dir = self.gui_dir.parent
        watch_dirs = [
            parent_dir / "utils",
            parent_dir / "project_init",
        ]
        
        for watch_dir in watch_dirs:
            if watch_dir.exists():
                self.observer.schedule(event_handler, str(watch_dir), recursive=True)
        
        self.observer.start()
        print(f"👀 Watching for changes in: {self.gui_dir}")
        print("💡 Save any .py file to trigger auto-reload")
        print("   Press Ctrl+C to stop the development server\n")
    
    def run(self):
        """Main run loop"""
        try:
            self.start_gui()
            self.setup_watcher()
            
            # Keep running until interrupted
            while self.running:
                time.sleep(1)
                # Check if process died unexpectedly
                if self.process and self.process.poll() is not None:
                    # Wait a moment to see if it's a reload
                    time.sleep(0.5)
                    if self.running and self.process.poll() is not None:
                        print("\n⚠️  GUI process exited")
                        break
        
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping development server...")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        self.running = False
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        if self.process and self.process.poll() is None:
            print("⏹️  Shutting down GUI...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        print("✅ Development server stopped")


def main():
    """Entry point"""
    runner = GUIRunner()
    runner.run()


if __name__ == "__main__":
    main()
