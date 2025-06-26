---
layout: wiki
title: Logging
permalink: /wiki/logging/
---

# Logging Processes in the Toolbox

The TI-Toolbox features its very own logging utility that provides a consistent and flexible way to handle logging across all components of the toolbox. This logging system is designed to be both powerful and easy to use, with support for both console and file output.

## Log Files

### Location and Structure

Log files are automatically stored in a structured directory hierarchy:
```
project_root/
└── derivatives/
    └── logs/
        └── sub-{subject_id}/
            └── {component_name}_{timestamp}.log
```

For example:
```
/mnt/projectdir/derivatives/logs/sub-010/analyzer_20250605_231026.log
```

### Reading Log Files

Log files contain detailed information about the execution of various toolbox components. Each log entry follows this format:
```
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Mesh analyzer initialized successfully
```

Breaking down the format:
- Timestamp: `[2025-06-05 23:10:26]`
- Component: `[analyzer.mesh_analyzer]`
- Log Level: `[INFO]`
- Message: `Mesh analyzer initialized successfully`

### Log Levels

Log entries are categorized by importance:
- **INFO**: General information about program execution
- **WARNING**: Warning messages for potentially problematic situations
- **ERROR**: Error messages for serious problems
- **DEBUG**: Detailed information for debugging (not shown by default)

## Real-World Examples

### Process Tracking

The logs show the progression of operations:

```
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Starting spherical ROI analysis (radius=5.0mm) at coordinates [-45.0, 0.0, 0.0]
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Loading mesh data...
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Creating spherical ROI at [-45.0, 0.0, 0.0] with radius 5.0mm...
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Found 45 nodes in the ROI
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Calculating statistics...
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Generating visualizations...
```

### Results and Statistics

Important results and statistics are logged with precise values:

```
[2025-06-05 23:10:26] [analyzer.mesh_analyzer.visualizer] [INFO] Data: 45 nodes, mean=0.032638, max=0.094988, min=0.009335
```

### Command Execution

External command execution is logged with full details:

```
[2025-06-05 23:10:27] [analyzer.mesh_analyzer] [INFO] Running: msh2cortex -i /mnt/projectdir/derivatives/SimNIBS/sub-010/Simulations/M1/TI/mesh/grey_010_M1_TI.msh -m /mnt/projectdir/derivatives/SimNIBS/sub-010/m2m_010 -o /mnt/projectdir/derivatives/SimNIBS/sub-010/Simulations/M1/TI/mesh
```

## Features

- **Dual Output**: Logs are written to both console and file simultaneously
- **Hierarchical Logging**: Support for parent-child logger relationships
- **External Logger Integration**: Ability to configure external loggers (e.g., SimNIBS)
- **Timestamped Log Files**: Automatic creation of timestamped log files
- **Configurable Formats**: Different formats for console and file output
- **Log Level Control**: Configurable logging levels
- **Bash Script Support**: Includes a bash wrapper for logging in shell scripts

## Environment Variables

The logging system respects the following environment variables:
- `TI_LOG_FILE`: Custom log file path (optional)
- `PROJECT_DIR`: Project root directory (required for default log file location)
- `SUBJECT_ID`: Subject identifier (required for default log file location)

## For Developers

### Python Usage

```python
from utils.logging_util import get_logger

# Create a logger with default settings
logger = get_logger('my_component')

# Log messages at different levels
logger.debug("Detailed information for debugging")
logger.info("General information about program execution")
logger.warning("Warning messages for potentially problematic situations")
logger.error("Error messages for serious problems")
```

### Bash Usage

```bash
# Source the logging utility
source utils/bash_logging.sh

# Initialize logging
init_logging "my_script" "/path/to/logfile.log"

# Log messages
log_info "This is an info message"
log_warning "This is a warning message"
log_error "This is an error message"
log_debug "This is a debug message"
```

### Advanced Features

#### Child Loggers

Create child loggers to maintain a hierarchical logging structure:

```python
# Create a parent logger
parent_logger = get_logger('parent')

# Create a child logger
child_logger = parent_logger.getChild('child')
```

The logger name hierarchy is reflected in the log output:
```
[2025-06-05 23:10:26] [parent] [INFO] Parent message
[2025-06-05 23:10:26] [parent.child] [INFO] Child message
```

#### External Logger Integration

Configure external loggers to use the same logging setup:

```python
from utils.logging_util import configure_external_loggers

# Configure external loggers to use the same handlers
configure_external_loggers(['simnibs', 'mesh_io'], parent_logger)
```

This ensures consistent logging across all components, including third-party libraries.

#### Custom Log File Location

Specify a custom log file location:

```python
logger = get_logger('my_component', log_file='/path/to/custom.log')
```

You can also set the log file path through the `TI_LOG_FILE` environment variable:
```bash
export TI_LOG_FILE="/path/to/custom.log"
```

## Best Practices

1. **Use Descriptive Logger Names**: Name loggers after the component they're used in
2. **Maintain Log Hierarchy**: Use child loggers for sub-components
3. **Appropriate Log Levels**: Use the appropriate log level for each message
4. **Structured Logging**: Include relevant context in log messages
5. **Error Handling**: Always log errors with sufficient context for debugging 