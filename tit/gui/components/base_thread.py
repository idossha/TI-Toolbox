#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Base Process Thread for TI-Toolbox GUI

Provides a unified, intelligent base class for all background process threads in the
TI-Toolbox GUI. Consolidates common patterns for subprocess execution, output parsing,
termination handling, and intelligent message type detection.

Key Features:
- Intelligent message type detection matching original SimulationThread logic
- Priority-based content analysis for accurate colorization
- Support for all TI-Toolbox scripts and external tools (SimNIBS, FSL, etc.)
- Cross-platform process management (Windows, Linux, macOS)
- Real-time output streaming with ANSI code stripping
- Proper process group handling for clean termination

Message Type Detection:
The base class provides sophisticated content-based detection that analyzes both
explicit tags ([ERROR], [WARNING], etc.) and message content patterns to determine
the appropriate message type for GUI display. This ensures consistent, intelligent
output formatting across all modules.

Usage:
    class MyCustomThread(BaseProcessThread):
        def run(self):
            '''Custom run implementation.'''
            # Setup command and environment
            self.cmd = ['python', 'my_script.py']
            self.env = os.environ.copy()

            # Call base class process execution
            self.execute_process()

        # Optionally override message type detection for custom logic
        def _detect_message_type(self, line_stripped, line_lower):
            # Add custom detection logic
            if 'my_special_pattern' in line_lower:
                return 'success'
            # Fall back to base class logic
            return super()._detect_message_type(line_stripped, line_lower)

Reusability:
This base class is designed to be reusable across all TI-Toolbox tabs and scripts:
- Simulator Tab: Direct Python execution or subprocess-based simulation
- Flex-Search Tab: Optimization processes
- Ex-Search Tab: Exhaustive search processes
- Analyzer Tab: Analysis workflows
- Pre-processing Tab: Multi-stage preprocessing pipelines
- Any custom scripts or external tool integrations
"""

import os
import signal
import subprocess
from PyQt5 import QtCore

from tit.gui.utils import strip_ansi_codes as _strip_ansi_codes_util


def detect_message_type_from_content(text):
    """Classify a subprocess output line for GUI color display.

    This is intentionally simple — structured log levels are not available
    for raw subprocess output, so we use heuristics.

    Returns one of: 'error', 'warning', 'success', 'info', 'debug', 'command', 'default'
    """
    t = text.lower()

    # Explicit tags take priority
    if "[error]" in t or "error:" in t or "traceback" in t or "exception" in t:
        return "error"
    if "✗ failed" in t or t.startswith("failed:") or t.startswith("critical:"):
        return "error"
    if "[warning]" in t or "warning:" in t or "warn:" in t:
        return "warning"
    if "[debug]" in t or "debug:" in t or "verbose:" in t:
        return "debug"
    if "✓" in text or "completed successfully" in t or "[success]" in t:
        return "success"
    if "===" in text or text.startswith("---"):
        return "command"
    if any(
        k in t for k in ("processing:", "starting", "loading", "saving", "generating")
    ):
        return "info"
    return "default"


class BaseProcessThread(QtCore.QThread):
    """
    Base class for all process-executing threads in TI-Toolbox.

    Provides unified, intelligent functionality for:
    - Subprocess execution with proper process group handling
    - Real-time output streaming with ANSI code stripping
    - Intelligent message type detection (error, warning, info, debug, success, command)
    - Process termination for both Windows and Unix systems
    - Signal emission for GUI updates

    Intelligent Message Type Detection:
    The _detect_message_type method uses sophisticated priority-based detection that
    analyzes message content to determine the appropriate type for GUI colorization.
    This matches the original SimulationThread logic and ensures consistent behavior
    across all TI-Toolbox scripts and modules.

    Message Type Classification:
    - ERROR (red, bold): [ERROR] tags, ERROR: prefix, exceptions, tracebacks, ✗ failed
    - WARNING (yellow): [WARNING] tags, Warning: prefix, caution keywords
    - SUCCESS (green, bold): ✓ symbols, "completed successfully", [SUCCESS]
    - INFO (cyan): "processing:", "starting", progress messages
    - COMMAND (blue): "executing:", "running", section headers (===, ---)
    - DEBUG (gray): [DEBUG] tags, debug: prefix
    - DEFAULT (white): All other informational messages

    Attributes:
        output_signal: PyQt signal emitting (message: str, type: str)
        error_signal: PyQt signal emitting (error_message: str)
        cmd: Command list to execute
        env: Environment variables dict
        process: subprocess.Popen instance
        terminated: Flag indicating if termination was requested

    Note:
        The QThread's built-in 'finished' signal is used for completion notification.
        This matches the original thread implementations in TI-Toolbox.

    Subclassing:
        Subclasses can override _detect_message_type() to add custom detection logic
        while still calling super()._detect_message_type() for fallback behavior.
    """

    # Common signals for all threads
    output_signal = QtCore.pyqtSignal(str, str)  # message, type
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, cmd=None, env=None, cwd=None, parent=None):
        """
        Initialize the base process thread.

        Args:
            cmd: Command list to execute (can be set later)
            env: Environment variables dict (defaults to os.environ.copy())
            cwd: Working directory for the subprocess (None = inherit)
            parent: Parent QObject
        """
        super(BaseProcessThread, self).__init__(parent)
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.cwd = cwd
        self.process = None
        self.terminated = False
        self.input_data = None  # Optional stdin lines (list[str])

    def run(self):
        """
        Default run implementation - subclasses should override this.

        Subclasses can either:
        1. Call self.execute_process() after setting self.cmd and self.env
        2. Implement their own run() method with custom logic
        """
        if self.cmd:
            self.execute_process()
        else:
            self.error_signal.emit("No command specified for execution")
            self.finished_signal.emit(False)

    def set_input_data(self, input_data):
        """Set stdin lines to send to the subprocess after launch.

        Args:
            input_data: List of strings to write to the process stdin.
        """
        self.input_data = input_data

    def execute_process(self):
        """
        Execute the subprocess with unified handling.

        This method:
        - Creates subprocess with proper process group
        - Optionally writes ``self.input_data`` to stdin
        - Streams output in real-time with ANSI stripping
        - Detects message types automatically
        - Handles process completion and errors
        - Emits appropriate signals
        """
        try:
            # Ensure Python output is unbuffered for real-time display
            self.env["PYTHONUNBUFFERED"] = "1"
            self.env["PYTHONFAULTHANDLER"] = "1"

            use_stdin = bool(self.input_data)

            # Create process with platform-specific process group handling
            if os.name == "nt":  # Windows
                self.process = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE if use_stdin else None,
                    universal_newlines=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    env=self.env,
                    cwd=self.cwd,
                )
            else:  # Unix/Linux/macOS
                self.process = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE if use_stdin else None,
                    universal_newlines=True,
                    bufsize=1,
                    preexec_fn=os.setsid,
                    env=self.env,
                    cwd=self.cwd,
                )

            # Write stdin data if provided
            if use_stdin:
                input_string = "\n".join(self.input_data) + "\n"
                try:
                    self.process.stdin.write(input_string)
                    self.process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    try:
                        self.process.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass

            # Stream output in real-time
            if self.process.stdout:
                for line in iter(self.process.stdout.readline, ""):
                    if self.terminated:
                        break

                    if line:
                        # Clean and process the line
                        raw_line = line.rstrip("\n")
                        line_clean = self._strip_ansi_codes(raw_line)
                        line_stripped = line_clean.strip()

                        if line_stripped:
                            # Detect message type
                            line_lower = line_stripped.lower()
                            message_type = self._detect_message_type(
                                line_stripped, line_lower
                            )

                            # Emit to GUI
                            self.output_signal.emit(line_stripped, message_type)

            # Wait for process completion if not terminated
            if not self.terminated:
                returncode = self.process.wait()
                if returncode != 0:
                    self.error_signal.emit(
                        f"Process returned non-zero exit code ({returncode})"
                    )

        except Exception as e:
            self.error_signal.emit(f"Error running process: {str(e)}")
        finally:
            # Ensure file descriptors are cleaned up
            if self.process:
                try:
                    if self.process.stdout:
                        self.process.stdout.close()
                except OSError:
                    pass
                try:
                    if self.process.stdin:
                        self.process.stdin.close()
                except OSError:
                    pass

    @staticmethod
    def _strip_ansi_codes(text):
        """Remove ANSI color/control sequences from text.

        Delegates to :func:`tit.gui.utils.strip_ansi_codes`.
        """
        return _strip_ansi_codes_util(text)

    def _detect_message_type(self, line_stripped, line_lower):
        """
        Intelligent message type detection from output line content.

        This method uses the shared detect_message_type_from_content() utility function
        to ensure consistent message classification across all TI-Toolbox components.

        Args:
            line_stripped: Cleaned line with whitespace stripped
            line_lower: Lowercase version of line_stripped (not used, kept for compatibility)

        Returns:
            Message type string: 'error', 'warning', 'info', 'debug',
                                'success', 'command', or 'default'

        Examples:
            >>> _detect_message_type("[ERROR] File not found", "[error] file not found")
            'error'
            >>> _detect_message_type("✓ Completed: montage_1", "✓ completed: montage_1")
            'success'
            >>> _detect_message_type("Processing: subject_01 (1/5)", "processing: subject_01 (1/5)")
            'info'
        """
        return detect_message_type_from_content(line_stripped)

    def terminate_process(self):
        """
        Terminate the running process and all its children.

        Handles both Windows and Unix systems with proper cleanup:
        - Windows: Uses taskkill with /T flag to kill process tree
        - Unix: Uses process group killing with SIGTERM then SIGKILL
        - Ensures graceful termination with timeout and force-kill fallback

        Returns:
            bool: True if termination was attempted, False if process not running
        """
        if self.process and self.process.poll() is None:  # Process is still running
            self.terminated = True

            if os.name == "nt":  # Windows
                # Use taskkill with /T flag to kill entire process tree
                try:
                    subprocess.call(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        stderr=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                    )
                except (OSError, subprocess.SubprocessError):
                    # Fallback: try direct kill
                    try:
                        self.process.kill()
                    except (OSError, ProcessLookupError):
                        # Process may have already terminated
                        pass

            else:  # Unix/Linux/macOS
                try:
                    # Kill the entire process group using SIGTERM first
                    pgid = os.getpgid(self.process.pid)
                    os.killpg(pgid, signal.SIGTERM)

                    # Wait briefly for graceful termination
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # If still running, force kill with SIGKILL
                        try:
                            os.killpg(pgid, signal.SIGKILL)
                        except (OSError, ProcessLookupError):
                            # Process group may have already terminated
                            pass

                        # Backup: force kill the main process directly
                        try:
                            self.process.kill()
                        except (OSError, ProcessLookupError):
                            # Process may have already terminated
                            pass

                except (OSError, ProcessLookupError):
                    # Fallback: try to kill the main process directly
                    try:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                    except (OSError, ProcessLookupError):
                        # Process may have already terminated
                        pass

            # Final cleanup - ensure process is terminated
            try:
                self.process.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError, ProcessLookupError):
                # Process may have already terminated or timed out
                pass

            return True

        return False


# Example usage and testing
if __name__ == "__main__":
    import sys
    from PyQt5 import QtWidgets

    class TestThread(BaseProcessThread):
        """Simple test thread that lists directory."""

        def run(self):
            if os.name == "nt":
                self.cmd = ["cmd", "/c", "dir"]
            else:
                self.cmd = ["ls", "-la"]

            self.execute_process()

    app = QtWidgets.QApplication(sys.argv)

    # Create and run test thread
    thread = TestThread()
    thread.output_signal.connect(lambda msg, typ: print(f"[{typ.upper()}] {msg}"))
    thread.error_signal.connect(lambda err: print(f"[ERROR SIGNAL] {err}"))
    thread.finished.connect(lambda: print(f"[FINISHED] Thread completed"))

    print("Starting test thread...")
    thread.start()
    thread.wait()

    print("\nTest completed!")
    sys.exit(0)
