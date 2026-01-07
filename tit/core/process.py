#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox Process Management Module
Unified process runner for all GUI tabs and command-line tools.
"""

from PyQt5 import QtCore

import os
import sys
import re
import subprocess
import signal
from typing import Optional, List, Dict, Callable, Any
import psutil

from .errors import ProcessError


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI color codes from text.

    Args:
        text: Text containing ANSI codes

    Returns:
        Cleaned text without ANSI codes
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def get_child_pids(parent_pid: int) -> List[int]:
    """
    Safely get child process IDs using psutil library.

    This function replaces the insecure shell=True subprocess calls
    that were vulnerable to command injection (B602 security issue).

    Args:
        parent_pid: Parent process ID

    Returns:
        List of child process IDs. Returns empty list if:
        - psutil is not available
        - parent process doesn't exist
        - access is denied
        - any other error occurs

    Security Note:
        This implementation is safe from command injection attacks
        as it uses the psutil library API instead of shell commands.
    """
    try:
        parent = psutil.Process(parent_pid)
        children = parent.children(recursive=False)
        return [child.pid for child in children]
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return []
    except Exception:
        # Catch any other unexpected errors, including psutil not available
        return []


class MessageParser:
    """
    Parse process output and determine message types.
    Base class that can be subclassed for tool-specific parsing.
    """
    
    def parse(self, line: str) -> tuple[str, str]:
        """
        Parse a line of output and return (cleaned_line, message_type).
        
        Args:
            line: Raw output line
            
        Returns:
            Tuple of (cleaned_line, message_type)
        """
        cleaned_line = strip_ansi_codes(line.strip())
        if not cleaned_line:
            return cleaned_line, 'default'
        
        # Determine message type based on content
        message_type = self._determine_message_type(cleaned_line)
        return cleaned_line, message_type
    
    def _determine_message_type(self, line: str) -> str:
        """
        Determine message type from line content.
        
        Args:
            line: Cleaned line text
            
        Returns:
            Message type: 'error', 'warning', 'success', 'info', 'command', 'debug', or 'default'
        """
        line_lower = line.lower()
        
        # Check for explicit tags first
        if '[ERROR]' in line or 'ERROR:' in line:
            return 'error'
        elif '[WARNING]' in line or 'Warning:' in line:
            return 'warning'
        elif '[INFO]' in line:
            return 'info'
        elif '[DEBUG]' in line:
            return 'debug'
        elif '[SUCCESS]' in line:
            return 'success'
        
        # Check for keyword patterns
        if any(keyword in line_lower for keyword in ['error:', 'critical:', 'failed', 'exception', 'traceback']):
            return 'error'
        elif any(keyword in line_lower for keyword in ['warning:', 'warn']):
            return 'warning'
        elif any(keyword in line_lower for keyword in ['executing:', 'running', 'command']):
            return 'command'
        elif any(keyword in line_lower for keyword in ['completed successfully', 'completed.', '✓ complete']):
            return 'success'
        elif any(keyword in line_lower for keyword in ['processing', 'starting', 'generating', 'loading']):
            return 'info'
        
        return 'default'


class ProcessRunner(QtCore.QThread):
    """
    Unified process runner for all GUI tabs.
    Handles subprocess execution with real-time output capture and proper termination.
    """
    
    # Signals
    output_signal = QtCore.pyqtSignal(str, str)  # (message, message_type)
    progress_signal = QtCore.pyqtSignal(int)  # progress percentage
    finished_signal = QtCore.pyqtSignal(int)  # exit code
    error_signal = QtCore.pyqtSignal(str)  # error message
    
    def __init__(
        self,
        cmd: List[str],
        env: Optional[Dict[str, str]] = None,
        stdin_data: Optional[List[str]] = None,
        message_parser: Optional[MessageParser] = None,
        cwd: Optional[str] = None
    ):
        """
        Initialize the process runner.
        
        Args:
            cmd: Command to execute as list of strings
            env: Environment variables (defaults to os.environ.copy())
            stdin_data: Optional list of lines to send to stdin
            message_parser: Optional custom message parser
            cwd: Optional working directory for the process
        """
        super().__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.stdin_data = stdin_data
        self.message_parser = message_parser or MessageParser()
        self.cwd = cwd
        self.process: Optional[subprocess.Popen] = None
        self.terminated = False
        
    def run(self):
        """Run the command in a separate thread."""
        try:
            # Ensure Python output is unbuffered
            self.env['PYTHONUNBUFFERED'] = '1'
            self.env['PYTHONFAULTHANDLER'] = '1'
            
            # Create process with appropriate platform-specific settings
            if os.name == 'nt':  # Windows
                self.process = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE if self.stdin_data else None,
                    universal_newlines=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    env=self.env,
                    cwd=self.cwd
                )
            else:  # Unix/Linux/Mac
                self.process = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE if self.stdin_data else None,
                    universal_newlines=True,
                    bufsize=1,
                    preexec_fn=os.setsid,  # Create new process group
                    env=self.env,
                    cwd=self.cwd
                )
            
            # Send stdin data if provided
            if self.stdin_data and self.process.stdin:
                try:
                    for line in self.stdin_data:
                        if self.terminated:
                            break
                        self.process.stdin.write(line + '\n')
                        self.process.stdin.flush()
                    self.process.stdin.close()
                except Exception as e:
                    self.error_signal.emit(f"Error sending stdin data: {str(e)}")
            
            # Read and emit output line by line
            if self.process.stdout:
                for line in iter(self.process.stdout.readline, ''):
                    if self.terminated:
                        break
                    if line:
                        cleaned_line, message_type = self.message_parser.parse(line)
                        if cleaned_line:
                            self.output_signal.emit(cleaned_line, message_type)
            
            # Wait for process completion if not terminated
            if not self.terminated:
                return_code = self.process.wait()
                self.finished_signal.emit(return_code)
                
                if return_code != 0:
                    error_msg = f"Process returned non-zero exit code: {return_code}"
                    self.output_signal.emit(error_msg, 'error')
                    self.error_signal.emit(error_msg)
                    
        except Exception as e:
            error_msg = f"Error running process: {str(e)}"
            self.output_signal.emit(error_msg, 'error')
            self.error_signal.emit(error_msg)
            self.finished_signal.emit(-1)
    
    def terminate_process(self) -> bool:
        """
        Terminate the running process.
        
        Returns:
            True if termination was attempted, False if process wasn't running
        """
        if not self.process or self.process.poll() is not None:
            return False  # Process not running
        
        self.terminated = True
        
        try:
            if os.name == 'nt':  # Windows
                # Terminate the entire process tree
                subprocess.call(
                    ['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:  # Unix/Linux/Mac
                # Try to terminate child processes using psutil (secure)
                try:
                    parent_pid = self.process.pid
                    child_pids = get_child_pids(parent_pid)
                    for pid in child_pids:
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except OSError:
                            pass  # Process might have already exited
                except Exception:
                    pass  # Ignore errors in finding/killing child processes
                
                # Terminate the main process
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()  # Force kill if it doesn't terminate gracefully
            
            return True
            
        except Exception as e:
            self.error_signal.emit(f"Error terminating process: {str(e)}")
            return False


class SimulatorMessageParser(MessageParser):
    """Message parser specifically for simulator output."""
    
    def _determine_message_type(self, line: str) -> str:
        """Override to add simulator-specific patterns."""
        # Check base patterns first
        base_type = super()._determine_message_type(line)
        if base_type != 'default':
            return base_type
        
        line_lower = line.lower()
        
        # Simulator-specific patterns
        if any(pattern in line_lower for pattern in [
            'beginning simulation',
            'montage visualization:',
            'simnibs simulation:',
            'field extraction:',
            'nifti transformation:',
            'results processing:'
        ]):
            return 'info'
        
        return 'default'


class AnalyzerMessageParser(MessageParser):
    """Message parser specifically for analyzer output."""
    
    def _determine_message_type(self, line: str) -> str:
        """Override to add analyzer-specific patterns."""
        base_type = super()._determine_message_type(line)
        if base_type != 'default':
            return base_type
        
        line_lower = line.lower()
        
        # Analyzer-specific patterns
        if any(pattern in line_lower for pattern in [
            'beginning analysis',
            'field data loading:',
            'cortical analysis:',
            'spherical analysis:',
            'results saving:',
            'analysis completed successfully'
        ]):
            return 'info'
        
        return 'default'


class PreprocessMessageParser(MessageParser):
    """Message parser specifically for preprocessing output."""
    
    def _determine_message_type(self, line: str) -> str:
        """Override to add preprocessing-specific patterns."""
        base_type = super()._determine_message_type(line)
        if base_type != 'default':
            return base_type
        
        line_lower = line.lower()
        
        # Preprocessing-specific patterns
        if any(pattern in line_lower for pattern in [
            'beginning pre-processing',
            'dicom conversion:',
            'simnibs charm:',
            'freesurfer recon-all:',
            'tissue analysis:',
            ': started',
            'pre-processing completed'
        ]):
            return 'info'
        
        if ': ✗ failed' in line_lower:
            return 'error'
        
        return 'default'


# Export public API
__all__ = [
    'ProcessRunner',
    'MessageParser',
    'SimulatorMessageParser',
    'AnalyzerMessageParser',
    'PreprocessMessageParser',
    'strip_ansi_codes',
]

