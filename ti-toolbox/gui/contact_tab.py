#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Contact Tab for TI-Toolbox GUI
This module provides a contact tab for users to reach out to developers.
"""

import os
import platform

from PyQt5 import QtWidgets, QtCore, QtGui

class ContactTab(QtWidgets.QWidget):
    """Contact tab for TI-Toolbox GUI."""
    
    def __init__(self, parent=None):
        super(ContactTab, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface for the contact tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create a scroll area
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        # Container widget for all content
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setAlignment(QtCore.Qt.AlignTop)
        content_layout.setSpacing(20)
        
        # Header
        header_label = QtWidgets.QLabel("<h1>Contact Information</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(header_label)
        
        # Introduction text
        intro_text = QtWidgets.QLabel(
            "<p>If you encounter issues, have questions, or would like to request new features, "
            "please feel free to reach out using one of the options below. Your feedback helps improve TI-Toolbox!</p>"
        )
        intro_text.setWordWrap(True)
        intro_text.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(intro_text)
        
        # Developer info card
        dev_card = self.create_developer_card()
        content_layout.addWidget(dev_card)
        
        # GitHub contribution section
        github_section = self.create_github_section()
        content_layout.addWidget(github_section)
        
        # Best practices section
        practices_section = self.create_best_practices_section()
        content_layout.addWidget(practices_section)
        
        # Set the content widget as the scroll area's widget
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
    
    def create_developer_card(self):
        """Create a card displaying developer information."""
        card = QtWidgets.QGroupBox("Main Developer")
        card_layout = QtWidgets.QVBoxLayout(card)
        
        # Create grid for contact details
        info_grid = QtWidgets.QGridLayout()
        info_grid.setColumnStretch(1, 1)
        info_grid.setVerticalSpacing(10)
        
        # Name
        name_label = QtWidgets.QLabel("<b>Name:</b>")
        name_value = QtWidgets.QLabel("Ido Haber")
        info_grid.addWidget(name_label, 0, 0)
        info_grid.addWidget(name_value, 0, 1)
        
        # Email
        email_label = QtWidgets.QLabel("<b>Email:</b>")
        email_value = QtWidgets.QLabel("ihaber@wisc.edu")
        info_grid.addWidget(email_label, 1, 0)
        info_grid.addWidget(email_value, 1, 1)
        
        # Affiliation
        affiliation_label = QtWidgets.QLabel("<b>Affiliation:</b>")
        affiliation_value = QtWidgets.QLabel("University of Wisconsin<br>Center for Sleep and Consciousness")
        info_grid.addWidget(affiliation_label, 2, 0)
        info_grid.addWidget(affiliation_value, 2, 1)
        
        # GitHub
        github_label = QtWidgets.QLabel("<b>GitHub:</b>")
        github_value = QtWidgets.QLabel("https://github.com/idossha/TI-Toolbox")
        info_grid.addWidget(github_label, 3, 0)
        info_grid.addWidget(github_value, 3, 1)
        
        card_layout.addLayout(info_grid)
        
        return card
    
    def create_github_section(self):
        """Create a section for GitHub issue reporting."""
        group = QtWidgets.QGroupBox("Contribute on GitHub")
        layout = QtWidgets.QVBoxLayout(group)
        
        # Description
        description = QtWidgets.QLabel(
            "<p>GitHub is our preferred platform for bug reports, feature requests, and community discussions. "
            "Choose from the options below depending on your needs:</p>"
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        
        # Content grid
        content_grid = QtWidgets.QGridLayout()
        content_grid.setColumnStretch(1, 1)
        content_grid.setVerticalSpacing(15)
        content_grid.setHorizontalSpacing(10)
        
        # Join Discussions
        discuss_icon = QtWidgets.QLabel()
        discuss_icon.setPixmap(QtGui.QIcon.fromTheme("forum").pixmap(32, 32))
        content_grid.addWidget(discuss_icon, 0, 0)
        
        discuss_info = QtWidgets.QVBoxLayout()
        discuss_title = QtWidgets.QLabel("<b>Join the Discussion & Share Ideas</b>")
        discuss_description = QtWidgets.QLabel("Have questions, ideas for improvements, or want to connect with other users? Visit our GitHub Discussions page to share your thoughts and join the community conversation. This is the best place to propose and discuss new features!")
        discuss_description.setWordWrap(True)
        discuss_info.addWidget(discuss_title)
        discuss_info.addWidget(discuss_description)
        content_grid.addLayout(discuss_info, 0, 1)
        
        # Report a Bug
        bug_icon = QtWidgets.QLabel()
        bug_icon.setPixmap(QtGui.QIcon.fromTheme("dialog-error").pixmap(32, 32))
        content_grid.addWidget(bug_icon, 1, 0)
        
        bug_info = QtWidgets.QVBoxLayout()
        bug_title = QtWidgets.QLabel("<b>Report a Bug</b>")
        bug_description = QtWidgets.QLabel("Found a problem? Let us know so we can fix it. Visit the GitHub issues page to report bugs.")
        bug_description.setWordWrap(True)
        bug_info.addWidget(bug_title)
        bug_info.addWidget(bug_description)
        content_grid.addLayout(bug_info, 1, 1)
        
        # Pull Requests
        pr_icon = QtWidgets.QLabel()
        pr_icon.setPixmap(QtGui.QIcon.fromTheme("document-edit").pixmap(32, 32))
        content_grid.addWidget(pr_icon, 2, 0)
        
        pr_info = QtWidgets.QVBoxLayout()
        pr_title = QtWidgets.QLabel("<b>Submit a Pull Request</b>")
        pr_description = QtWidgets.QLabel("Already implemented a fix or feature? Submit a pull request through GitHub to contribute your code.")
        pr_description.setWordWrap(True)
        pr_info.addWidget(pr_title)
        pr_info.addWidget(pr_description)
        content_grid.addLayout(pr_info, 2, 1)
        
        layout.addLayout(content_grid)
        
        return group
    
    def create_best_practices_section(self):
        """Create a section for communication best practices."""
        group = QtWidgets.QGroupBox("Communication Best Practices")
        layout = QtWidgets.QVBoxLayout(group)
        
        practices = QtWidgets.QTextEdit()
        practices.setReadOnly(True)
        practices.setHtml("""
        <h3>When Reporting Bugs:</h3>
        <ul>
            <li><b>Be specific:</b> Include a clear, concise title that summarizes the issue</li>
            <li><b>Provide context:</b> Describe what you were doing when the bug occurred</li>
            <li><b>Detail steps to reproduce:</b> Number each step so developers can follow along</li>
            <li><b>Include system info:</b> Operating system, TI-Toolbox version, and relevant configuration</li>
            <li><b>Add screenshots:</b> If applicable, visual evidence helps tremendously</li>
        </ul>
        
        <h3>When Requesting Features:</h3>
        <ul>
            <li><b>Describe the problem:</b> Explain what challenge you're facing first</li>
            <li><b>Propose a solution:</b> Suggest how the feature might work</li>
            <li><b>Explain the benefit:</b> Clarify who would benefit and how</li>
            <li><b>Be patient:</b> Feature requests are considered carefully alongside other priorities</li>
        </ul>
        
        <h3>When Submitting Pull Requests:</h3>
        <ul>
            <li><b>Reference issues:</b> Link to any related issue(s)</li>
            <li><b>Keep changes focused:</b> Address one concern per pull request</li>
            <li><b>Follow code style:</b> Match the existing code style and conventions</li>
            <li><b>Include tests:</b> Add tests for new functionality when possible</li>
            <li><b>Update documentation:</b> Ensure docs reflect your changes</li>
        </ul>
        """)
        practices.setMinimumHeight(250)
        layout.addWidget(practices)
        
        return group
    
    def get_icon(self, icon_name):
        """Get an icon based on name."""
        if icon_name == "email":
            return QtGui.QIcon.fromTheme("mail-send")
        elif icon_name == "github":
            return QtGui.QIcon.fromTheme("github")
        else:
            return QtGui.QIcon() 
