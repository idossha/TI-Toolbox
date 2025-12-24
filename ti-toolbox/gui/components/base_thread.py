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
import re
import signal
import subprocess
from PyQt5 import QtCore


def detect_message_type_from_content(text):
    """
    Intelligent message type detection from text content.
    
    This is a standalone utility function that can be used by any component
    (threads, handlers, etc.) to classify messages for GUI display.
    
    Priority order (matching original SimulationThread logic):
    1. Explicit error/warning tags or prefixes
    2. Explicit level tags ([INFO], [DEBUG], etc.) for external logger compatibility
    3. Command/execution keywords (executing:, running, command)
    4. Success indicators (✓, completed successfully)
    5. Progress/status messages (processing:, starting)
    6. Section headers (===, ---)
    7. Error keywords (error:, exception, traceback, failed)
    8. Additional warning/debug/info patterns
    9. Default (regular informational messages)
    
    Args:
        text: The message text to classify (should be cleaned of ANSI codes)
        
    Returns:
        str: Message type - 'error', 'warning', 'info', 'debug', 'success', 'command', or 'default'
        
    Examples:
        >>> detect_message_type_from_content("[ERROR] File not found")
        'error'
        >>> detect_message_type_from_content("✓ Completed: montage_1")
        'success'
        >>> detect_message_type_from_content("Processing: subject_01 (1/5)")
        'info'
    """
    text_lower = text.lower()
    
    # Priority 1: Explicit error/warning tags or prefixes
    is_error_tag = '[ERROR]' in text or 'ERROR:' in text
    if is_error_tag:
        return 'error'
    elif '[WARNING]' in text or 'Warning:' in text:
        return 'warning'
        
    # Priority 2: Explicit level tags (for compatibility with external loggers)
    elif '[INFO]' in text:
        return 'info'
    elif '[DEBUG]' in text:
        return 'debug'
        
    # Priority 3: Content-based detection for command/execution messages
    elif any(keyword in text_lower for keyword in ['executing:', 'running', 'command']):
        return 'command'
        
    # Priority 4: Success indicators
    elif (text.startswith('[SUCCESS]') or 
          ('completed successfully' in text_lower and 'debug' not in text_lower) or
          ('✓ completed:' in text_lower) or
          (text_lower.startswith('✓') and 'completed' in text_lower) or
          ('✓ complete' in text_lower)):
        return 'success'
        
    # Priority 5: Progress/status messages (processing, starting)
    elif any(keyword in text_lower for keyword in ['processing:', 'starting', 'processing subject']):
        return 'info'
        
    # Priority 6: Section headers and structural elements
    elif '===' in text or text.startswith('---'):
        return 'command'
        
    # Priority 7: Error keywords (more specific to avoid false positives)
    elif (text_lower.startswith('error:') or
          text_lower.startswith('critical:') or
          'exception' in text_lower or
          'traceback' in text_lower or
          text_lower.startswith('failed:') or
          '✗ failed:' in text_lower):
        return 'error'

    # Priority 8: Additional warning patterns
    elif any(keyword in text_lower for keyword in ['warning:', 'warn:', 'caution']):
        return 'warning'

    # Priority 9: Additional debug patterns
    elif any(keyword in text_lower for keyword in ['debug:', 'verbose:']):
        return 'debug'

    # Priority 10: Additional info patterns for common operations
    elif any(keyword in text_lower for keyword in ['generating', 'loading', 'saving', 'creating']):
        return 'info'

    # Default: regular informational messages (displayed in white)
    else:
        return 'default'


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

    # ANSI escape sequence pattern (consolidated from multiple implementations)
    ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self, cmd=None, env=None, parent=None):
        """
        Initialize the base process thread.

        Args:
            cmd: Command list to execute (can be set later)
            env: Environment variables dict (defaults to os.environ.copy())
            parent: Parent QObject
        """
        super(BaseProcessThread, self).__init__(parent)
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.process = None
        self.terminated = False

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

    def execute_process(self):
        """
        Execute the subprocess with unified handling.

        This method:
        - Creates subprocess with proper process group
        - Streams output in real-time with ANSI stripping
        - Detects message types automatically
        - Handles process completion and errors
        - Emits appropriate signals
        """
        try:
            # Ensure Python output is unbuffered for real-time display
            self.env['PYTHONUNBUFFERED'] = '1'
            self.env['PYTHONFAULTHANDLER'] = '1'

            # Create process with platform-specific process group handling
            if os.name == 'nt':  # Windows
                self.process = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Combine streams
                    universal_newlines=True,
                    bufsize=1,  # Line buffered
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    env=self.env
                )
            else:  # Unix/Linux/macOS
                self.process = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Combine streams
                    universal_newlines=True,
                    bufsize=1,  # Line buffered
                    preexec_fn=os.setsid,  # Create new process group
                    env=self.env
                )

            # Stream output in real-time
            if self.process.stdout:
                for line in iter(self.process.stdout.readline, ''):
                    if self.terminated:
                        break

                    if line:
                        # Clean and process the line
                        raw_line = line.rstrip('\n')
                        line_clean = self._strip_ansi_codes(raw_line)
                        line_stripped = line_clean.strip()

                        if line_stripped:
                            # Detect message type
                            line_lower = line_stripped.lower()
                            message_type = self._detect_message_type(line_stripped, line_lower)

                            # Emit to GUI
                            self.output_signal.emit(line_stripped, message_type)

            # Wait for process completion if not terminated
            if not self.terminated:
                returncode = self.process.wait()
                if returncode != 0:
                    # Note: Non-zero exit codes don't necessarily mean failure
                    # (e.g., SimNIBS may return warnings). Just log it.
                    self.error_signal.emit(f"Process returned non-zero exit code ({returncode})")

        except Exception as e:
            self.error_signal.emit(f"Error running process: {str(e)}")

    def _strip_ansi_codes(self, text):
        """
        Remove ANSI color/control sequences from text.

        Args:
            text: String potentially containing ANSI escape codes

        Returns:
            Cleaned string with ANSI codes removed
        """
        if not text:
            return text

        # Remove ANSI sequences
        cleaned = self.ANSI_ESCAPE_PATTERN.sub('', text)

        # Remove any stray ESC characters
        cleaned = cleaned.replace('\x1b', '')

        return cleaned

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

            if os.name == 'nt':  # Windows
                # Use taskkill with /T flag to kill entire process tree
                try:
                    subprocess.call(
                        ['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                        stderr=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL
                    )
                except Exception:
                    # Fallback: try direct kill
                    try:
                        self.process.kill()
                    except Exception:
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
                        except Exception:
                            pass

                        # Backup: force kill the main process directly
                        try:
                            self.process.kill()
                        except Exception:
                            pass

                except Exception:
                    # Fallback: try to kill the main process directly
                    try:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                    except Exception:
                        pass

            # Final cleanup - ensure process is terminated
            try:
                self.process.wait(timeout=1)
            except Exception:
                pass

            return True

        return False


# Example usage and testing
if __name__ == '__main__':
    import sys
    from PyQt5 import QtWidgets

    class TestThread(BaseProcessThread):
        """Simple test thread that lists directory."""

        def run(self):
            if os.name == 'nt':
                self.cmd = ['cmd', '/c', 'dir']
            else:
                self.cmd = ['ls', '-la']

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
