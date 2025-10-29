# Electrode Placement GUI

A simple, fast graphical interface for placing electrode markers on 3D head surfaces.

## Features

- **Fast Loading**: Quickly load skin and gray matter surfaces from m2m directories
- **3D Visualization**: Interactive OpenGL-based 3D rendering
- **Easy Marker Placement**: Double-click to place electrode markers on the surface
- **Coordinate Collection**: Automatic collection of XYZ coordinates in a table
- **Export**: Save coordinates to CSV format

## Requirements

```bash
pip install PyQt5 PyOpenGL
```

SimNIBS must be installed and accessible in your Python environment.

## Usage

### Starting the GUI

```bash
python electrode_placement_gui.py
```

### Loading a Subject

1. Click **Browse** and select your `m2m_subjectID` directory, or manually enter the path
2. Click **Load Surfaces** to load the mesh
3. The skin surface will be displayed by default

### Placing Markers

1. **Double-click** anywhere on the surface to place a marker
2. The marker appears as a red sphere
3. Coordinates are automatically added to the table

### 3D Navigation

- **Rotate**: Left-click and drag
- **Translate**: Right-click and drag  
- **Zoom**: Mouse scroll wheel

### Viewing Surfaces

- Toggle between **Skin** and **Gray Matter** using the radio buttons
- Markers remain in place when switching surfaces

### Managing Markers

- **Delete Selected**: Select a row in the table and click to remove that marker
- **Clear All**: Remove all markers at once
- **Save Coordinates**: Export all marker coordinates to a CSV file

## Output Format

Saved CSV files have the following format:

```csv
Marker,X,Y,Z
1,45.23,67.89,123.45
2,23.45,78.90,134.56
...
```

Coordinates are in the same coordinate system as the mesh file (typically MNI space for m2m models).

## Keyboard Shortcuts

Currently, the GUI uses mouse-only interaction for simplicity. Future versions may add:
- Delete key to remove selected marker
- Ctrl+S to save
- Ctrl+C to clear all

## Tips

1. **Accurate Placement**: Zoom in before placing markers for better precision
2. **Naming**: Marker numbers are automatically assigned sequentially
3. **Multiple Sessions**: You can load, place markers, save, and repeat with different subjects
4. **Surface Selection**: Place markers on the skin surface for scalp electrodes, or GM surface for target visualization

## Technical Details

### File Structure

The GUI expects the following structure:
```
m2m_subjectID/
├── subjectID.msh    # Main mesh file (or any .msh file)
└── ...
```

### Surface Tags

- Skin surface: Tags 5 and 1005
- Gray matter: Tags 2 and 1002

These are standard SimNIBS surface tags.

## Troubleshooting

### "SimNIBS not available" error
- Ensure SimNIBS is properly installed
- Activate the SimNIBS environment before running the GUI

### Mesh file not found
- Make sure you're selecting the correct m2m directory
- The directory should contain a `.msh` file

### OpenGL errors
- Update your graphics drivers
- On some systems, you may need to set `PYOPENGL_PLATFORM=osmesa`

### Slow rendering
- Large meshes (>100k triangles) may render slowly
- The code is optimized for typical head meshes (~50k triangles)

## Comparison to Full GUI

This simplified version focuses on electrode placement only. For full simulation capabilities, use the main TI-Toolbox GUI with features like:
- Field simulation
- Multiple montage comparison
- Optimization
- And more...

## Future Enhancements

Potential additions (not yet implemented):
- Named markers (e.g., "Cz", "F3")
- Load existing marker sets
- Marker color coding
- Distance measurements between markers
- Import/export in multiple formats

## License

This tool is part of the TI-Toolbox project. See main LICENSE file.

