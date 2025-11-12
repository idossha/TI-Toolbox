#!/usr/bin/env python3
"""
Benchmark logging utilities with file flushing support.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional


class FlushingFileHandler(logging.FileHandler):
    """File handler that flushes after every write."""
    
    def emit(self, record):
        """Emit a record and flush immediately."""
        super().emit(record)
        self.flush()


class FlushingStreamHandler(logging.StreamHandler):
    """Stream handler that flushes after every write."""
    
    def emit(self, record):
        """Emit a record and flush immediately."""
        super().emit(record)
        self.flush()


class BenchmarkLogger:
    """
    Logger for benchmark operations with automatic flushing.
    
    Provides both console and file logging with immediate flushing
    to ensure no data is lost in case of crashes or interruptions.
    """
    
    def __init__(
        self,
        name: str,
        log_file: Optional[Path] = None,
        debug_mode: bool = True,
        console_output: bool = True
    ):
        """
        Initialize the benchmark logger.
        
        Args:
            name: Name for the logger
            log_file: Optional path to log file
            debug_mode: If True, use DEBUG level; if False, use INFO level
            console_output: If True, also output to console
        """
        self.name = name
        self.log_file = log_file
        self.debug_mode = debug_mode
        self.console_output = console_output
        
        # Create logger
        self.logger = logging.getLogger(f"benchmark.{name}")
        self.logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Create formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Add file handler if log file specified
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = FlushingFileHandler(str(log_file))
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        
        # Add console handler if requested
        if console_output:
            console_handler = FlushingStreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(message)
    
    def info(self, message: str):
        """Log info message."""
        self.logger.info(message)
    
    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)
    
    def error(self, message: str):
        """Log error message."""
        self.logger.error(message)
    
    def critical(self, message: str):
        """Log critical message."""
        self.logger.critical(message)
    
    def separator(self, char: str = "=", length: int = 70):
        """Log a separator line."""
        self.info(char * length)
    
    def header(self, text: str, char: str = "=", length: int = 70):
        """Log a header with separator lines."""
        self.separator(char, length)
        self.info(text.center(length))
        self.separator(char, length)


def create_benchmark_log_file(
    benchmark_name: str,
    output_dir: Path,
    subject_id: Optional[str] = None
) -> Path:
    """
    Create a timestamped log file path for a benchmark.
    
    Args:
        benchmark_name: Name of the benchmark
        output_dir: Directory to store log files
        subject_id: Optional subject ID to include in filename
        
    Returns:
        Path to the log file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if subject_id:
        filename = f"{benchmark_name}_{subject_id}_{timestamp}.log"
    else:
        filename = f"{benchmark_name}_{timestamp}.log"
    
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    return log_dir / filename


if __name__ == "__main__":
    # Demo usage
    print("Benchmark Logger Demo")
    
    # Create a test log file
    log_file = Path("/tmp/benchmark_test.log")
    
    # Create logger
    logger = BenchmarkLogger(
        name="test",
        log_file=log_file,
        debug_mode=True,
        console_output=True
    )
    
    # Log some messages
    logger.header("BENCHMARK TEST")
    logger.info("This is an info message")
    logger.debug("This is a debug message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.separator()
    
    print(f"\nLog file created at: {log_file}")

