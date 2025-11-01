---
layout: wiki
title: Quick Notes
permalink: /wiki/quick-notes/
---

The Quick Notes extension provides a simple note-taking tool for documenting observations, decisions, and insights during sessions. Notes are automatically timestamped and persistently stored in the project directory.


## Key Features

- **Automatic Timestamping**: Every note includes precise timestamp with timezone information
- **Persistent Storage**: Notes saved to project directory following BIDS conventions
- **Session Continuity**: Notes persist across TI-Toolbox restarts
- **Copy to Clipboard**: Easy export of notes for reports or presentations
- **Clean Formatting**: Structured display with separators and chronological ordering


### Note Format

Each note follows a consistent structure:

```
Note #1:
[2024-11-01 14:30:45 EST]
This is my observation about the hippocampal stimulation results.
The field strength appears optimal at 2.3 V/m for this electrode configuration.

----------------------------------------------------------------------
```

## Usage Workflow

### Basic Note-Taking

1. **Launch Extension**: Settings → Extensions → "Quick Notes"
2. **Compose Note**: Type observations in the input area
3. **Add Note**: Click "Add Note" to timestamp and save
4. **Review History**: Scroll through previous notes in the display area

## Technical Details

### Storage Location

Notes are saved following BIDS derivatives structure:

```
project_dir/
└── derivatives/
    └── ti-toolbox/
        └── notes.txt
```

This ensures notes are:
- **Project-specific**: Associated with the correct dataset
- **Backup-compatible**: Included in standard data backup procedures
- **Collaboration-friendly**: Accessible to all researchers working on the project

### Timestamp Format

Notes use ISO 8601 format with timezone information:

```
YYYY-MM-DD HH:MM:SS TZ
```

**Examples:**
- `2024-11-01 14:30:45 EST` (Eastern Standard Time)
- `2024-11-01 19:30:45 UTC` (Coordinated Universal Time)
- `2024-11-01 11:30:45 PST` (Pacific Standard Time)

### Timezone Handling

The extension automatically detects the host system's timezone:

```python
# Automatic timezone detection
tz_name = os.environ.get('TZ', 'UTC')
# Falls back gracefully for systems without timezone info
```

## Troubleshooting

### Common Issues

**"No project directory detected"**
- Ensure TI-Toolbox is properly initialized with a project directory
- Check that the project follows BIDS structure
- Verify write permissions to the derivatives directory

**Timezone display issues**
- Check system timezone settings
- Extension falls back to UTC if timezone detection fails
- Notes remain functional regardless of timezone display

**File access errors**
- Verify write permissions to project directory
- Check for file locking by other applications
- Ensure sufficient disk space for notes file

### Data Recovery

**Notes File Location:**
- Primary: `project/derivatives/ti-toolbox/notes.txt`
- Backup: Check TI-Toolbox log files for any error messages
- Recovery: Notes are plain text and can be edited manually if needed

