#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Example Extension: Quick Notes
A simple note-taking extension for recording observations during analysis.
"""

from PyQt5 import QtWidgets, QtCore
from datetime import datetime

# Extension metadata (required)
EXTENSION_NAME = "Quick Notes"
EXTENSION_DESCRIPTION = "Take quick notes during your analysis sessions with timestamps."


class NotesWindow(QtWidgets.QDialog):
    """Quick notes window."""
    
    def __init__(self, parent=None):
        super(NotesWindow, self).__init__(parent)
        self.setWindowTitle("Quick Notes")
        self.setMinimumSize(600, 500)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the notes UI."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Header
        header_label = QtWidgets.QLabel("<h2>Quick Notes</h2>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Info label
        info_label = QtWidgets.QLabel(
            "<i>Take quick notes with automatic timestamps. Notes are kept in memory for this session only.</i>"
        )
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
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        button_layout.addWidget(add_btn)
        
        clear_btn = QtWidgets.QPushButton("Clear All Notes")
        clear_btn.clicked.connect(self.clear_all_notes)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        button_layout.addWidget(clear_btn)
        
        copy_btn = QtWidgets.QPushButton("Copy All to Clipboard")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        button_layout.addWidget(copy_btn)
        
        input_layout.addLayout(button_layout)
        layout.addWidget(input_group)
        
        # Store notes
        self.notes = []
    
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
        
        # Get current timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Add to notes list
        formatted_note = f"[{timestamp}]\n{note_text}\n"
        self.notes.append(formatted_note)
        
        # Update display
        self.update_notes_display()
        
        # Clear input
        self.note_input.clear()
    
    def update_notes_display(self):
        """Update the notes display area."""
        display_text = ""
        for i, note in enumerate(self.notes, 1):
            display_text += f"Note #{i}:\n{note}\n{'-' * 70}\n\n"
        
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

