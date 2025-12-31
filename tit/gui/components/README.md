# GUI Components

This directory contains reusable UI components for the TI-Toolbox GUI.

## Components

### ConsoleWidget

A reusable console output widget with associated controls.

**Features:**
- Dark-themed console output (QTextEdit)
- Optional Clear Console button
- Optional Debug Mode checkbox
- Auto-scrolling when user is at bottom
- Colored output based on message type
- ANSI escape sequence handling

**Usage Example:**

```python
from components.console import ConsoleWidget

# Create console widget
console_widget = ConsoleWidget(
    parent=self,
    show_clear_button=True,
    show_debug_checkbox=True,
    console_label="Output:",
    min_height=200,
    max_height=300  # Optional, None for unlimited
)

# Add to layout
layout.addWidget(console_widget)

# Update console with colored messages
console_widget.update_console("Processing started...", 'info')
console_widget.update_console("Operation successful!", 'success')
console_widget.update_console("Warning: Low memory", 'warning')
console_widget.update_console("Error occurred!", 'error')

# Get underlying QTextEdit if needed
text_edit = console_widget.get_console_widget()

# Check debug mode status
if console_widget.is_debug_mode():
    console_widget.update_console("Debug information", 'debug')
```

**Message Types:**
- `'default'` - White text
- `'info'` - Cyan text
- `'success'` - Green text
- `'warning'` - Yellow text
- `'error'` - Red text (bold)
- `'debug'` - Gray text (filtered out when debug mode is off)
- `'command'` - Blue text

**Parameters:**
- `parent` - Parent widget
- `show_clear_button` - Show Clear Console button (default: True)
- `show_debug_checkbox` - Show Debug Mode checkbox (default: True)
- `console_label` - Label text for console header (None to hide)
- `min_height` - Minimum height in pixels (default: 200)
- `max_height` - Maximum height in pixels (None for unlimited)

## Implementation Status

✅ **ConsoleWidget** - Implemented and integrated into tabs
⏸️  Other tabs (Simulator, Ex-Search, Flex-Search, Analyzer, etc.) - Ready to migrate when requested

## Benefits

1. **Code Reusability** - Write once, use everywhere
2. **Consistency** - Same look and behavior across all tabs
3. **Maintainability** - Fix bugs and add features in one place
4. **Easy Customization** - Simple parameters to customize appearance
5. **Cleaner Code** - Reduces duplicate code in individual tabs

