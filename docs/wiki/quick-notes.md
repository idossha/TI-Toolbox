---
layout: wiki
title: Quick Notes
permalink: /wiki/quick-notes/
---

The Quick Notes extension provides a simple yet powerful note-taking tool for documenting observations, decisions, and insights during temporal interference (TI) stimulation analysis sessions. Notes are automatically timestamped and persistently stored in the project directory for reproducibility and collaboration.

## Overview

Quick Notes addresses the critical need for documentation in neuroimaging research workflows. During complex analysis sessions involving multiple simulations, statistical tests, and visualization iterations, researchers often need to record observations, parameter choices, and unexpected findings. This extension provides an always-accessible note-taking interface that integrates seamlessly with the TI-Toolbox workflow.

## Key Features

- **Automatic Timestamping**: Every note includes precise timestamp with timezone information
- **Persistent Storage**: Notes saved to project directory following BIDS conventions
- **Session Continuity**: Notes persist across TI-Toolbox restarts
- **Copy to Clipboard**: Easy export of notes for reports or presentations
- **Clean Formatting**: Structured display with separators and chronological ordering
- **Host Timezone Detection**: Automatic timezone detection from system settings

## User Interface

The Quick Notes interface provides an intuitive note-taking experience:

### Main Window Layout

- **Header**: Clear identification and file location information
- **Notes Display**: Read-only area showing all existing notes in chronological order
- **Input Area**: Text editor for composing new notes
- **Action Buttons**: Add, clear, and copy functionality

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

### Session Documentation

**Example Research Session:**

```
[2024-11-01 09:15:23 EST]
Starting hippocampal stimulation optimization for Subject 001.
Using Flex Search with target ROI: left hippocampus (atlas region 35).
Electrode radius: 8mm, current: 1mA, optimization goal: maximize mean field.

[2024-11-01 09:45:12 EST]
Flex Search completed. Final electrode positions show good coverage
of target ROI. Peak field: 3.8 V/m, mean ROI field: 2.1 V/m.
Focality (75% threshold): 2,340 mm².

[2024-11-01 10:02:47 EST]
SimNIBS simulation running. Note: increased mesh density in temporal
lobe to improve field accuracy near hippocampus.

[2024-11-01 11:30:15 EST]
Simulation completed successfully. TI field analysis shows excellent
targeting with minimal spread to adjacent cortical areas.
Proceeding to next subject.
```

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

### File Format

Notes are stored in plain text format for maximum compatibility:

```
TI-Toolbox Quick Notes
======================

Note #1:
[2024-11-01 14:30:45 EST]
First observation about the data analysis.

----------------------------------------------------------------------
Note #2:
[2024-11-01 14:35:22 EST]
Second observation with additional details.

----------------------------------------------------------------------
```

## Integration with Research Workflow

### Documentation Best Practices

**Recommended Note Categories:**

- **Parameter Choices**: Document why specific analysis parameters were selected
- **Unexpected Findings**: Record anomalies or interesting observations
- **Decision Points**: Explain choices between alternative analysis approaches
- **Quality Control**: Note data quality issues or preprocessing decisions
- **Future Work**: Ideas for follow-up analyses or experiments

### Collaboration Features

**Multi-User Scenarios:**

- **Shared Notes**: All team members can read existing notes
- **Individual Sessions**: Each user can add their own observations
- **Chronological Record**: Complete timeline of analysis decisions
- **Context Preservation**: Notes linked to specific analysis sessions

### Export and Reporting

**Copy to Clipboard**: Export notes for inclusion in:

- **Lab Meeting Presentations**: Share findings with colleagues
- **Manuscript Methods**: Document analysis procedures
- **Grant Reports**: Demonstrate research progress
- **Data Management Plans**: Show reproducible workflows

## Advanced Usage

### Custom Workflows

**Structured Note Templates:**

```
[2024-11-01 09:00:00 EST]
SUBJECT: sub-001
SIMULATION: HIPP_L_stimulation
PARAMETERS:
- Target ROI: Left hippocampus
- Electrode configuration: 4×8mm
- Current amplitude: 1mA
- Optimization method: Flex Search
RESULTS:
- Peak field: 3.8 V/m
- Mean ROI field: 2.1 V/m
- Focality: 2,340 mm²
NOTES: Good targeting, minimal spread to adjacent areas
```

**Analysis Session Logging:**

```
SESSION START: Hippocampal Stimulation Optimization
Date: 2024-11-01
Researcher: Dr. Smith
Objective: Optimize electrode positions for bilateral hippocampal stimulation

[09:15] Flex Search configuration completed
[09:45] Optimization converged after 1500 evaluations
[10:02] SimNIBS simulation initiated
[11:30] Results analysis completed
[11:45] Session concluded - proceeding to statistical analysis

SESSION END
```

### Integration with Other Tools

**Cross-Tool Documentation:**

- **Flex Search**: Record optimization parameters and convergence behavior
- **Ex Search**: Document leadfield matrix performance and target selection
- **Analyzer**: Note field analysis settings and statistical thresholds
- **Nilearn Visuals**: Record visualization parameters and figure choices
- **CBP Testing**: Document statistical analysis parameters and interpretations

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

### Performance Considerations

- **File I/O**: Minimal impact on system performance
- **Memory Usage**: Lightweight interface with small memory footprint
- **Storage**: Text files typically < 100KB for extensive research sessions
- **Backup**: Include notes.txt in standard data backup procedures

## Best Practices

### Documentation Guidelines

**When to Take Notes:**

- **Parameter Selection**: Record why specific values were chosen
- **Unexpected Results**: Document anomalies or interesting findings
- **Method Changes**: Note modifications to analysis procedures
- **Quality Issues**: Record data quality concerns or preprocessing decisions
- **Collaboration Points**: Share insights with team members

**Note Content Guidelines:**

- **Be Specific**: Include concrete values, not just general observations
- **Context Matters**: Reference specific subjects, simulations, or analysis steps
- **Actionable**: Notes should help reproduce or understand the analysis
- **Concise**: Focus on key information without unnecessary detail

### Research Reproducibility

**Reproducibility Enhancement:**

- **Parameter Documentation**: Record all analysis settings
- **Decision Rationale**: Explain why certain choices were made
- **Version Information**: Note TI-Toolbox and dependency versions
- **Data Issues**: Document any data quality concerns addressed
- **Future Reference**: Enable other researchers to understand and build upon the work

## Future Developments

**Planned Enhancements:**

- **Rich Text Support**: Formatting options for emphasis and structure
- **Tag System**: Categorize notes by topic or analysis type
- **Search Functionality**: Find specific notes within long sessions
- **Export Formats**: PDF or HTML export for sharing
- **Integration**: Direct links to specific analysis results or visualizations
- **Collaboration**: Multi-user editing with conflict resolution
