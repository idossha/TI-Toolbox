#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Example Extension: Quick Notes
A simple note-taking extension for recording observations during analysis.
Notes are automatically saved to projectDIR/derivatives/ti-toolbox/notes.txt
"""

import os
from pathlib import Path
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for older Python versions
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)
from PyQt5 import QtWidgets, QtCore

# Extension metadata (required)
EXTENSION_NAME = "Quick Notes"
EXTENSION_DESCRIPTION = "Take quick notes during your analysis sessions with timestamps."

from tit.core import get_path_manager


class NotesWindow(QtWidgets.QDialog):
    """Quick notes window with persistent storage."""
    
    def __init__(self, parent=None):
        super(NotesWindow, self).__init__(parent)
        self.setWindowTitle("Quick Notes")
        self.setMinimumSize(600, 500)
        
        # Initialize path manager and notes file path
        self.pm = get_path_manager() if get_path_manager else None
        self.notes_file_path = None
        self.notes = []
        
        # Determine notes file path
        self._setup_notes_file_path()
        
        # Load existing notes if available
        self._load_notes()
        
        self.setup_ui()
    
    def _setup_notes_file_path(self):
        """Set up the notes file path using path manager."""
        if not self.pm:
            return
        
        project_dir = self.pm.project_dir
        if not project_dir:
            return
        
        # Create derivatives/ti-toolbox directory if it doesn't exist
        ti_toolbox_dir = os.path.join(project_dir, "derivatives", "ti-toolbox")
        os.makedirs(ti_toolbox_dir, exist_ok=True)
        
        # Set notes file path
        self.notes_file_path = os.path.join(ti_toolbox_dir, "notes.txt")
    
    def _load_notes(self):
        """Load notes from file if it exists."""
        if not self.notes_file_path or not os.path.exists(self.notes_file_path):
            return

        try:
            with open(self.notes_file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    # Parse notes (they're separated by separator lines)
                    note_blocks = content.split('\n' + '-' * 70 + '\n')
                    self.notes = []
                    for block in note_blocks:
                        block = block.strip()
                        if block:
                            # Remove "Note #X:" prefix if present (for backward compatibility)
                            lines = block.split('\n', 1)
                            if len(lines) > 0 and lines[0].startswith('Note #'):
                                # Remove the "Note #X:" line and keep only the content
                                note_content = lines[1] if len(lines) > 1 else ''
                                self.notes.append(note_content.strip())
                            else:
                                # If no prefix, treat the whole block as the note
                                self.notes.append(block)
        except (IOError, OSError) as e:
            print(f"Error loading notes: {e}")
    
    def _save_notes(self):
        """Save notes to file."""
        if not self.notes_file_path:
            return

        try:
            with open(self.notes_file_path, 'w', encoding='utf-8') as f:
                for i, note in enumerate(self.notes):
                    f.write(f"{note}\n")
                    # Only add separator if not the last note
                    if i < len(self.notes) - 1:
                        f.write('-' * 70 + '\n\n')
        except (IOError, OSError) as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Save Error",
                f"Could not save notes: {e}"
            )
    
    def _get_timestamp_with_timezone(self):
        """Get current timestamp with timezone from host machine."""
        import os
        # Use the host timezone passed from the loader
        tz_name = os.environ.get('TZ', 'UTC')
        try:
            tz = ZoneInfo(tz_name)
            dt = datetime.now(tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception as e:
            # Fallback if timezone is invalid or zoneinfo not available
            print(f"Warning: Could not use timezone '{tz_name}': {e}")
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def setup_ui(self):
        """Set up the notes UI."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Header
        header_label = QtWidgets.QLabel("<h2>Quick Notes</h2>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Info label
        project_dir_name = self.pm.project_dir_name if self.pm else None
        info_text = f"<i>Notes are saved to: /mnt/{project_dir_name}/derivatives/ti-toolbox/notes.txt</i>"
        
        info_label = QtWidgets.QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        info_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(info_label)
        
        # Notes display area
        display_group = QtWidgets.QGroupBox("Your Notes")
        display_layout = QtWidgets.QVBoxLayout(display_group)
        
        self.notes_display = QtWidgets.QTextEdit()
        self.notes_display.setReadOnly(True)
        self.notes_display.setStyleSheet("""
            QTextEdit {
                font-family: monospace;
                font-size: 12px;
                background-color: #f9f9f9;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        display_layout.addWidget(self.notes_display)
        layout.addWidget(display_group)
        
        # Input area
        input_group = QtWidgets.QGroupBox("Add New Note")
        input_layout = QtWidgets.QVBoxLayout(input_group)
        
        self.note_input = QtWidgets.QTextEdit()
        self.note_input.setMaximumHeight(100)
        self.note_input.setPlaceholderText("Type your note here...")
        self.note_input.setStyleSheet("""
            QTextEdit {
                font-size: 12px;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        input_layout.addWidget(self.note_input)
        
        # Button row
        button_layout = QtWidgets.QHBoxLayout()
        
        add_btn = QtWidgets.QPushButton("Add Note")
        add_btn.clicked.connect(self.add_note)
        button_layout.addWidget(add_btn)
        
        clear_btn = QtWidgets.QPushButton("Clear All Notes")
        clear_btn.clicked.connect(self.clear_all_notes)
        button_layout.addWidget(clear_btn)
        
        copy_btn = QtWidgets.QPushButton("Copy All to Clipboard")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        button_layout.addWidget(copy_btn)
        
        input_layout.addLayout(button_layout)
        layout.addWidget(input_group)
        
        # Update display with loaded notes
        self.update_notes_display()
    
    def add_note(self):
        """Add a new note with timestamp."""
        note_text = self.note_input.toPlainText().strip()
        
        if not note_text:
            QtWidgets.QMessageBox.warning(
                self,
                "Empty Note",
                "Please enter some text before adding a note."
            )
            return
        
        # Get current timestamp with timezone
        timestamp = self._get_timestamp_with_timezone()
        
        # Add to notes list
        formatted_note = f"[{timestamp}]\n{note_text}"
        self.notes.append(formatted_note)
        
        # Save to file
        self._save_notes()
        
        # Update display
        self.update_notes_display()
        
        # Clear input
        self.note_input.clear()
    
    def update_notes_display(self):
        """Update the notes display area."""
        display_text = ""
        for note in self.notes:
            display_text += f"{note}\n\n{'-' * 70}\n\n"

        self.notes_display.setPlainText(display_text)
        
        # Scroll to bottom
        cursor = self.notes_display.textCursor()
        cursor.movePosition(cursor.End)
        self.notes_display.setTextCursor(cursor)
    
    def clear_all_notes(self):
        """Clear all notes after confirmation."""
        if not self.notes:
            QtWidgets.QMessageBox.information(
                self,
                "No Notes",
                "There are no notes to clear."
            )
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear All Notes",
            "Are you sure you want to clear all notes? This cannot be undone.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.notes = []
            self.notes_display.clear()
            self._save_notes()
    
    def copy_to_clipboard(self):
        """Copy all notes to clipboard."""
        if not self.notes:
            QtWidgets.QMessageBox.information(
                self,
                "No Notes",
                "There are no notes to copy."
            )
            return
        
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.notes_display.toPlainText())
        
        QtWidgets.QMessageBox.information(
            self,
            "Copied",
            "All notes have been copied to the clipboard."
        )


def main(parent=None):
    """
    Main entry point for the extension.
    This function is called when the extension is launched.
    """
    notes_window = NotesWindow(parent)
    notes_window.exec_()


# Alternative entry point (for flexibility)
def run(parent=None):
    """Alternative entry point."""
    main(parent)

