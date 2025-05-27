from qt_compat import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, Qt, QTimer, QFont


class ProgressWidget(QWidget):
    """Widget to show Docker-style progress bars for layer downloads"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(200)
        self.layer_widgets = {}  # Track progress bars for each layer
        self.setup_ui()
        
        # Auto-cleanup timer
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.cleanup_completed)
        self.cleanup_timer.start(5000)  # Clean up every 5 seconds
    
    def setup_ui(self):
        """Setup the progress widget UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # Header
        header = QLabel("Download Progress")
        header.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        header.setStyleSheet("color: #2c3e50; margin-bottom: 5px;")
        layout.addWidget(header)
        
        # Progress container
        self.progress_container = QVBoxLayout()
        layout.addLayout(self.progress_container)
        layout.addStretch()
        
        # Hide initially
        self.hide()
    
    def add_layer_progress(self, layer_id, status, percentage):
        """Add or update progress for a layer"""
        # Only show widget if we actually have meaningful progress to display
        # This reduces unnecessary flickering for quick operations
        if not self.isVisible() and (percentage > 0 or "downloading" in status.lower() or "pull" in status.lower()):
            self.show()
            
        if layer_id not in self.layer_widgets:
            self._create_layer_widget(layer_id)
        
        # Update the widgets
        layer_widget = self.layer_widgets[layer_id]
        label = layer_widget['label']
        progress_bar = layer_widget['progress']
        
        # Truncate layer ID for display
        display_id = layer_id[:12] if len(layer_id) > 12 else layer_id
        label.setText(f"{display_id}: {status}")
        progress_bar.setValue(percentage)
        
        # Mark as completed if 100%
        if percentage >= 100:
            layer_widget['completed'] = True
            progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #c3e6cb;
                    border-radius: 3px;
                    background-color: #d4edda;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #28a745;
                    border-radius: 2px;
                }
            """)
    
    def _create_layer_widget(self, layer_id):
        """Create progress widget for a new layer"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Layer label
        label = QLabel(f"{layer_id[:12]}: Initializing...")
        label.setFixedWidth(200)
        label.setFont(QFont("Courier", 9))
        
        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(100)
        progress_bar.setValue(0)
        progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #dee2e6;
                border-radius: 3px;
                background-color: #f8f9fa;
                text-align: center;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: #007bff;
                border-radius: 2px;
            }
        """)
        
        layout.addWidget(label)
        layout.addWidget(progress_bar)
        
        # Store references
        self.layer_widgets[layer_id] = {
            'container': container,
            'label': label,
            'progress': progress_bar,
            'completed': False
        }
        
        # Add to layout
        self.progress_container.addWidget(container)
        
        # Limit number of visible progress bars
        if len(self.layer_widgets) > 5:
            self._cleanup_oldest()
    
    def _cleanup_oldest(self):
        """Remove the oldest progress bar if too many are shown"""
        if not self.layer_widgets:
            return
            
        # Find oldest (first) widget
        oldest_id = next(iter(self.layer_widgets))
        self._remove_layer_widget(oldest_id)
    
    def cleanup_completed(self):
        """Clean up completed progress bars"""
        to_remove = []
        for layer_id, widget_info in self.layer_widgets.items():
            if widget_info.get('completed', False):
                to_remove.append(layer_id)
        
        # Only clean up if we have multiple completed items to avoid flicker
        if len(to_remove) > 1:
            for layer_id in to_remove[:-1]:  # Keep the last completed item for a bit longer
                QTimer.singleShot(3000, lambda lid=layer_id: self._remove_layer_widget(lid))
    
    def _remove_layer_widget(self, layer_id):
        """Remove a layer's progress widget"""
        if layer_id in self.layer_widgets:
            widget_info = self.layer_widgets[layer_id]
            container = widget_info['container']
            
            # Remove from layout and delete
            self.progress_container.removeWidget(container)
            container.deleteLater()
            del self.layer_widgets[layer_id]
            
            # Only hide widget if no more progress bars and no recent activity
            if not self.layer_widgets:
                # Add a small delay before hiding to prevent flicker
                QTimer.singleShot(1000, self.hide)
    
    def clear_all(self):
        """Clear all progress bars"""
        for layer_id in list(self.layer_widgets.keys()):
            self._remove_layer_widget(layer_id)
        self.hide()


class StoppableOperationWidget(QWidget):
    """Widget with a stop button for long operations"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.hide()
    
    def setup_ui(self):
        """Setup the stop button UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        self.status_label = QLabel("Operation in progress...")
        self.status_label.setStyleSheet("color: #495057; font-weight: bold;")
        
        self.stop_button = QPushButton("⏹️ Stop Operation")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        
        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(self.stop_button)
    
    def set_status(self, status):
        """Set the status text"""
        self.status_label.setText(status)
    
    def show_operation(self, status="Operation in progress..."):
        """Show the widget with status"""
        self.set_status(status)
        self.show()
    
    def hide_operation(self):
        """Hide the widget"""
        self.hide() 