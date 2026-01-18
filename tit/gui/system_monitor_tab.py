#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox-2.0 System Monitor Tab
This module provides a GUI interface for monitoring toolbox-related processes.
Shows CPU, memory usage, and process information for relevant operations.
"""

import os
import sys
import psutil
import subprocess
import time
import threading
from datetime import datetime
from collections import deque

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QHeaderView

import matplotlib

matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

plt.style.use("dark_background")  # Use dark theme for graphs


class ProcessMonitorThread(QThread):
    """Thread to monitor system processes without blocking the GUI."""

    process_data_signal = pyqtSignal(list)  # List of process data
    system_stats_signal = pyqtSignal(dict)  # System-wide stats

    def __init__(self):
        super().__init__()
        self.running = True
        self.update_interval = 2.0  # Update every 2 seconds

        # Keywords to identify toolbox-related processes
        self.relevant_keywords = [
            "charm",
            "simnibs",
            "freesurfer",
            "recon-all",
            "dcm2niix",
            "fsl",
            "bet",
            "fast",
            "first",
            "flirt",
            "fnirt",
            "pre_process.py",
            "pre/structural.py",
            "pre/dicom2nifti.py",
            "pre/charm.py",
            "pre/recon_all.py",
            "ti_sim.py",
            "flex-search.py",
            "ex-search",
            "leadfield.py",
            "mesh_field_analyzer.py",
            "main-TI.sh",
            "main-mTI.sh",
            "simulator",
            "python.*TI",
            "matlab.*sim",
            "gmsh",
            "tetgen",
            "subject_atlas",
            "mri_convert",
            "mris_",
            "mri_",
            "fs_",
            "preprocessor",
            "field_extract",
            "mesh2nii",
        ]

    def run(self):
        """Main monitoring loop."""
        while self.running:
            try:
                # Get system-wide statistics
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()

                system_stats = {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_used": memory.used,
                    "memory_total": memory.total,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                }
                self.system_stats_signal.emit(system_stats)

                # Get relevant processes
                relevant_processes = self.get_relevant_processes()
                self.process_data_signal.emit(relevant_processes)

                time.sleep(self.update_interval)

            except Exception as e:
                print(f"Error in process monitoring: {e}")
                time.sleep(self.update_interval)

    def get_relevant_processes(self):
        """Get processes relevant to the toolbox using psutil."""
        relevant_processes = []

        try:
            for proc in psutil.process_iter(
                [
                    "pid",
                    "name",
                    "cmdline",
                    "cpu_percent",
                    "memory_percent",
                    "create_time",
                    "status",
                ]
            ):
                try:
                    proc_info = proc.info
                    cmdline = (
                        " ".join(proc_info["cmdline"]) if proc_info["cmdline"] else ""
                    )
                    proc_name = proc_info["name"] or ""

                    # Check if process is relevant
                    if self.is_relevant_process(proc_name, cmdline):
                        # Calculate runtime
                        runtime = time.time() - proc_info["create_time"]
                        runtime_str = self.format_runtime(runtime)

                        # Format memory usage
                        memory_mb = 0
                        try:
                            memory_info = proc.memory_info()
                            memory_mb = memory_info.rss / (1024 * 1024)  # Convert to MB
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            pass

                        process_data = {
                            "pid": proc_info["pid"],
                            "name": proc_name,
                            "cmdline": (
                                cmdline[:100] + "..." if len(cmdline) > 100 else cmdline
                            ),  # Truncate long commands
                            "cpu_percent": proc_info["cpu_percent"] or 0,
                            "memory_percent": proc_info["memory_percent"] or 0,
                            "memory_mb": memory_mb,
                            "runtime": runtime_str,
                            "status": proc_info["status"],
                        }
                        relevant_processes.append(process_data)

                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue

        except Exception as e:
            print(f"Error getting process list: {e}")

        # Sort by CPU usage (descending)
        relevant_processes.sort(key=lambda x: x["cpu_percent"], reverse=True)
        return relevant_processes

    def get_processes_fallback(self):
        """Fallback method to get processes without psutil."""
        relevant_processes = []

        try:
            # Use ps command on Unix-like systems
            if os.name != "nt":
                cmd = ["ps", "aux"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")[1:]  # Skip header

                    for line in lines:
                        parts = line.split(None, 10)  # Split into max 11 parts
                        if len(parts) >= 11:
                            user, pid, cpu, mem = parts[0], parts[1], parts[2], parts[3]
                            command = parts[10]

                            if self.is_relevant_process("", command):
                                process_data = {
                                    "pid": int(pid),
                                    "name": (
                                        command.split()[0] if command else "unknown"
                                    ),
                                    "cmdline": (
                                        command[:100] + "..."
                                        if len(command) > 100
                                        else command
                                    ),
                                    "cpu_percent": (
                                        float(cpu)
                                        if cpu.replace(".", "").isdigit()
                                        else 0
                                    ),
                                    "memory_percent": (
                                        float(mem)
                                        if mem.replace(".", "").isdigit()
                                        else 0
                                    ),
                                    "memory_mb": 0,
                                    "runtime": "N/A",
                                    "status": "running",
                                }
                                relevant_processes.append(process_data)
        except Exception as e:
            print(f"Error in fallback process detection: {e}")

        return relevant_processes

    def is_relevant_process(self, proc_name, cmdline):
        """Check if a process is relevant to the toolbox."""
        search_text = f"{proc_name} {cmdline}".lower()

        # Check against our keywords
        for keyword in self.relevant_keywords:
            if keyword.lower() in search_text:
                return True

        # Additional checks for Python processes running toolbox scripts
        if "python" in search_text and any(
            term in search_text
            for term in [
                "ti-",
                "gui/",
                "pre-process/",
                "simulator/",
                "flex-search/",
                "ex-search/",
            ]
        ):
            return True

        return False

    def format_runtime(self, seconds):
        """Format runtime in a human-readable way."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def stop(self):
        """Stop the monitoring thread."""
        self.running = False


class SystemMonitorTab(QtWidgets.QWidget):
    """Tab for monitoring system resources and toolbox processes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.monitor_thread = None

        # Data storage for graphs (store last 60 data points = 2 minutes at 2-second intervals)
        self.max_data_points = 60
        self.cpu_data = deque(maxlen=self.max_data_points)
        self.memory_data = deque(maxlen=self.max_data_points)
        self.time_data = deque(maxlen=self.max_data_points)

        self.setup_ui()
        self.start_monitoring()

    def setup_ui(self):
        """Set up the user interface for the system monitor tab."""
        main_layout = QtWidgets.QVBoxLayout(self)

        # Title and description
        title_label = QtWidgets.QLabel("System Monitor")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        description_label = QtWidgets.QLabel(
            "Monitor toolbox-related processes including pre-processing, simulations, and optimizations."
        )
        description_label.setWordWrap(True)

        main_layout.addWidget(title_label)
        main_layout.addWidget(description_label)
        main_layout.addSpacing(10)

        # System stats section
        stats_group = QtWidgets.QGroupBox("System Overview")
        stats_layout = QtWidgets.QHBoxLayout(stats_group)

        # CPU usage
        self.cpu_label = QtWidgets.QLabel("CPU: 0%")
        self.cpu_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        # Memory usage
        self.memory_label = QtWidgets.QLabel("Memory: 0%")
        self.memory_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        # Last update
        self.update_label = QtWidgets.QLabel("Last Update: --:--:--")
        self.update_label.setStyleSheet("color: #666666;")

        stats_layout.addWidget(self.cpu_label)
        stats_layout.addWidget(self.memory_label)
        stats_layout.addStretch()
        stats_layout.addWidget(self.update_label)

        main_layout.addWidget(stats_group)

        # Process table
        processes_group = QtWidgets.QGroupBox("Active Toolbox Processes")
        processes_layout = QtWidgets.QVBoxLayout(processes_group)

        # Create process table
        self.process_table = QtWidgets.QTableWidget()
        self.process_table.setColumnCount(7)
        self.process_table.setHorizontalHeaderLabels(
            [
                "PID",
                "Process Name",
                "Command",
                "CPU %",
                "Memory %",
                "Memory (MB)",
                "Runtime",
            ]
        )

        # Set table properties
        self.process_table.setAlternatingRowColors(True)
        self.process_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.process_table.setSortingEnabled(True)

        # Set column widths
        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # PID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Process Name
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Command
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # CPU %
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Memory %
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Memory MB
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Runtime

        processes_layout.addWidget(self.process_table)

        # Control buttons
        controls_layout = QtWidgets.QHBoxLayout()

        self.refresh_btn = QtWidgets.QPushButton("Manual Refresh")
        self.refresh_btn.clicked.connect(self.manual_refresh)

        self.pause_btn = QtWidgets.QPushButton("Pause Monitoring")
        self.pause_btn.clicked.connect(self.toggle_monitoring)

        self.clear_graphs_btn = QtWidgets.QPushButton("Clear Graphs")
        self.clear_graphs_btn.clicked.connect(self.clear_graph_data)
        self.clear_graphs_btn.setStyleSheet("background-color: #555; color: white;")

        self.kill_btn = QtWidgets.QPushButton("Terminate Selected Process")
        self.kill_btn.clicked.connect(self.terminate_selected_process)
        self.kill_btn.setStyleSheet("background-color: #f44336; color: white;")

        controls_layout.addWidget(self.refresh_btn)
        controls_layout.addWidget(self.pause_btn)
        controls_layout.addWidget(self.clear_graphs_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(self.kill_btn)

        processes_layout.addLayout(controls_layout)
        main_layout.addWidget(processes_group)

        # Real-time graphs section
        graphs_group = QtWidgets.QGroupBox("Real-time Performance Graphs")
        graphs_layout = QtWidgets.QHBoxLayout(graphs_group)

        # Create matplotlib figures
        self.setup_graphs()

        # Add graphs to layout
        graphs_layout.addWidget(self.cpu_canvas)
        graphs_layout.addWidget(self.memory_canvas)

        main_layout.addWidget(graphs_group)

        # Status label
        self.status_label = QtWidgets.QLabel("Monitoring active...")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        main_layout.addWidget(self.status_label)

    def setup_graphs(self):
        """Set up the matplotlib graphs for CPU and memory monitoring."""
        # Set up CPU graph
        self.cpu_figure = Figure(figsize=(6, 3), dpi=80)
        self.cpu_canvas = FigureCanvas(self.cpu_figure)
        self.cpu_canvas.setMinimumHeight(200)

        self.cpu_ax = self.cpu_figure.add_subplot(111)
        self.cpu_ax.set_title("CPU Usage (%)", color="white", fontsize=12, pad=10)
        self.cpu_ax.set_xlabel("Time (seconds ago)", color="white")
        self.cpu_ax.set_ylabel("CPU %", color="white")
        self.cpu_ax.set_ylim(0, 100)
        self.cpu_ax.grid(True, alpha=0.3)
        self.cpu_ax.tick_params(colors="white")

        # Initialize empty line for CPU
        (self.cpu_line,) = self.cpu_ax.plot(
            [], [], "cyan", linewidth=2, label="CPU Usage"
        )
        self.cpu_ax.legend(loc="upper right")

        # Set up Memory graph
        self.memory_figure = Figure(figsize=(6, 3), dpi=80)
        self.memory_canvas = FigureCanvas(self.memory_figure)
        self.memory_canvas.setMinimumHeight(200)

        self.memory_ax = self.memory_figure.add_subplot(111)
        self.memory_ax.set_title("Memory Usage (%)", color="white", fontsize=12, pad=10)
        self.memory_ax.set_xlabel("Time (seconds ago)", color="white")
        self.memory_ax.set_ylabel("Memory %", color="white")
        self.memory_ax.set_ylim(0, 100)
        self.memory_ax.grid(True, alpha=0.3)
        self.memory_ax.tick_params(colors="white")

        # Initialize empty line for Memory
        (self.memory_line,) = self.memory_ax.plot(
            [], [], "orange", linewidth=2, label="Memory Usage"
        )
        self.memory_ax.legend(loc="upper right")

        # Style the figures
        self.cpu_figure.patch.set_facecolor("#2b2b2b")
        self.memory_figure.patch.set_facecolor("#2b2b2b")

        # Set axes background to black
        self.cpu_ax.set_facecolor("black")
        self.memory_ax.set_facecolor("black")

        # Tight layout to prevent label cutoff
        self.cpu_figure.tight_layout()
        self.memory_figure.tight_layout()

    def start_monitoring(self):
        """Start the process monitoring thread."""
        if self.monitor_thread is None or not self.monitor_thread.isRunning():
            # Clear graph data when starting fresh
            self.clear_graph_data()

            self.monitor_thread = ProcessMonitorThread()
            self.monitor_thread.process_data_signal.connect(self.update_process_table)
            self.monitor_thread.system_stats_signal.connect(self.update_system_stats)
            self.monitor_thread.start()
            self.status_label.setText("Monitoring active...")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.pause_btn.setText("Pause Monitoring")

    def stop_monitoring(self):
        """Stop the process monitoring thread."""
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            self.monitor_thread.wait(3000)  # Wait up to 3 seconds
            self.status_label.setText("Monitoring paused")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.pause_btn.setText("Resume Monitoring")

    def clear_graph_data(self):
        """Clear the graph data when monitoring is restarted."""
        self.cpu_data.clear()
        self.memory_data.clear()
        self.time_data.clear()
        if hasattr(self, "cpu_line"):
            self.cpu_line.set_data([], [])
            self.memory_line.set_data([], [])
            self.cpu_canvas.draw()
            self.memory_canvas.draw()

    def toggle_monitoring(self):
        """Toggle monitoring on/off."""
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def manual_refresh(self):
        """Manually refresh the process list."""
        if self.monitor_thread and self.monitor_thread.isRunning():
            # Thread will update automatically, just show feedback
            self.status_label.setText("Refreshing...")
            QtCore.QTimer.singleShot(
                1000, lambda: self.status_label.setText("Monitoring active...")
            )

    def update_system_stats(self, stats):
        """Update system-wide statistics display."""
        self.cpu_label.setText(f"CPU: {stats['cpu_percent']:.1f}%")

        if stats["memory_total"] > 0:
            memory_gb = stats["memory_used"] / (1024**3)
            total_gb = stats["memory_total"] / (1024**3)
            self.memory_label.setText(
                f"Memory: {stats['memory_percent']:.1f}% ({memory_gb:.1f}/{total_gb:.1f} GB)"
            )
        else:
            self.memory_label.setText(f"Memory: {stats['memory_percent']:.1f}%")

        self.update_label.setText(f"Last Update: {stats['timestamp']}")

        # Update graphs
        if hasattr(self, "cpu_line"):
            self.update_graphs(stats)

    def update_graphs(self, stats):
        """Update the real-time graphs with new data."""
        # Get current time for x-axis (seconds since start)
        current_time = time.time()
        if len(self.time_data) == 0:
            # First data point - set as time 0
            self.start_time = current_time
            relative_time = 0
        else:
            # Calculate relative time in seconds
            relative_time = current_time - self.start_time

        # Add new data points
        self.time_data.append(relative_time)
        self.cpu_data.append(stats["cpu_percent"])
        self.memory_data.append(stats["memory_percent"])

        # Convert to lists for plotting (deque to list)
        times = list(self.time_data)
        cpu_values = list(self.cpu_data)
        memory_values = list(self.memory_data)

        # Create x-axis as "seconds ago" (reverse the time scale)
        if len(times) > 1:
            max_time = max(times)
            x_axis = [max_time - t for t in times]
        else:
            x_axis = [0]

        # Update CPU graph
        self.cpu_line.set_data(x_axis, cpu_values)
        self.cpu_ax.set_xlim(
            0, max(60, max(x_axis) if x_axis else 60)
        )  # Show at least 60 seconds
        self.cpu_ax.set_ylim(0, max(100, max(cpu_values) if cpu_values else 100))

        # Update Memory graph
        self.memory_line.set_data(x_axis, memory_values)
        self.memory_ax.set_xlim(
            0, max(60, max(x_axis) if x_axis else 60)
        )  # Show at least 60 seconds
        self.memory_ax.set_ylim(
            0, max(100, max(memory_values) if memory_values else 100)
        )

        # Refresh the canvases
        self.cpu_canvas.draw()
        self.memory_canvas.draw()

    def update_process_table(self, processes):
        """Update the process table with new data."""
        # Store current selection
        selected_row = self.process_table.currentRow()
        selected_pid = None
        if selected_row >= 0 and self.process_table.rowCount() > selected_row:
            pid_item = self.process_table.item(selected_row, 0)
            if pid_item:
                selected_pid = int(pid_item.text())

        # Clear and repopulate table
        self.process_table.setRowCount(len(processes))

        for row, proc in enumerate(processes):
            # PID
            self.process_table.setItem(
                row, 0, QtWidgets.QTableWidgetItem(str(proc["pid"]))
            )

            # Process Name
            self.process_table.setItem(row, 1, QtWidgets.QTableWidgetItem(proc["name"]))

            # Command
            self.process_table.setItem(
                row, 2, QtWidgets.QTableWidgetItem(proc["cmdline"])
            )

            # CPU %
            cpu_item = QtWidgets.QTableWidgetItem(f"{proc['cpu_percent']:.1f}%")
            if proc["cpu_percent"] > 50:
                cpu_item.setBackground(
                    QtGui.QColor(255, 200, 200)
                )  # Light red for high CPU
            self.process_table.setItem(row, 3, cpu_item)

            # Memory %
            mem_item = QtWidgets.QTableWidgetItem(f"{proc['memory_percent']:.1f}%")
            if proc["memory_percent"] > 10:
                mem_item.setBackground(
                    QtGui.QColor(255, 200, 200)
                )  # Light red for high memory
            self.process_table.setItem(row, 4, mem_item)

            # Memory MB
            self.process_table.setItem(
                row, 5, QtWidgets.QTableWidgetItem(f"{proc['memory_mb']:.1f}")
            )

            # Runtime
            self.process_table.setItem(
                row, 6, QtWidgets.QTableWidgetItem(proc["runtime"])
            )

        # Restore selection if possible
        if selected_pid:
            for row in range(self.process_table.rowCount()):
                pid_item = self.process_table.item(row, 0)
                if pid_item and int(pid_item.text()) == selected_pid:
                    self.process_table.selectRow(row)
                    break

    def terminate_selected_process(self):
        """Terminate the selected process."""
        current_row = self.process_table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(
                self, "No Selection", "Please select a process to terminate."
            )
            return

        pid_item = self.process_table.item(current_row, 0)
        name_item = self.process_table.item(current_row, 1)

        if not pid_item or not name_item:
            return

        pid = int(pid_item.text())
        process_name = name_item.text()

        # Confirm termination
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Termination",
            f"Are you sure you want to terminate process:\n\n"
            f"PID: {pid}\n"
            f"Name: {process_name}\n\n"
            f"This action cannot be undone.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                QtWidgets.QMessageBox.information(
                    self, "Success", f"Process {pid} terminated successfully."
                )
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self, "Error", f"Failed to terminate process {pid}:\n{str(e)}"
                )

    def closeEvent(self, event):
        """Clean up when the tab is closed."""
        self.stop_monitoring()
        super().closeEvent(event)
