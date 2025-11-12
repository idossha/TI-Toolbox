# Montage Visualizer Test

This test suite verifies the functionality of `montage_visualizer.py` for creating electrode montage visualizations on the GSN-256.png template image.

## Test Overview

The test creates visualizations for the following montages:
- **GSN-256 Network**: E010-E011 and E012-E013 electrode pairs
- **10-10 Network**: Fp2-AF8 and F10-FT10 electrode pairs

Both unipolar and multipolar simulation modes are tested.

## Files Structure

```
test/
├── montage_visualizer.py          # Main visualization script
├── test_montage_visualizer.py     # Test suite
├── amv/                          # Resources directory
│   ├── GSN-256.csv               # GSN-256 electrode coordinates
│   ├── 10-10.csv                 # 10-10 electrode coordinates
│   ├── GSN-256.png               # Template image
│   └── pair1ring.png to pair8ring.png  # Ring overlay images
└── output/                       # Generated visualizations
```

## Running the Tests

### Run Unit Tests
```bash
python3 test_montage_visualizer.py
```

### Run Demo Mode
```bash
python3 test_montage_visualizer.py --demo
```

The demo mode will:
1. Create montage configurations for the requested montages
2. Generate visualizations for both GSN-256 and 10-10 networks
3. Test both unipolar and multipolar modes
4. Save output files to the `output/` directory

## Generated Output Files

### Unipolar Mode (Separate images per montage)
- `E010-E011_highlighted_visualization.png`
- `E012-E013_highlighted_visualization.png`
- `Fp2-AF8_highlighted_visualization.png`
- `F10-FT10_highlighted_visualization.png`

### Multipolar Mode (Combined image)
- `combined_montage_visualization.png` (overwrites for each test)

## Ring Image Improvements

**Issue**: Original rings were low-resolution and poorly positioned.

**Solution**: Created precisely-sized ring images with 40px radius:
- **Size**: 100×100 pixels (compact for 40px radius rings)
- **Design**: Rings are perfectly centered at (50,50) within each image
- **Colors**: 8 distinct colors avoiding red, white, black, grey: chartreuse, deepskyblue, lime, gold, hotpink, turquoise, violet, orange
- **Style**: Single hollow circle with thick stroke (6px)
- **Size**: 40px radius (approximately 27% of original 150px size)
- **Transparency**: Proper alpha channel for clean overlay on template

**Ring Specifications** (40px radius):
- Radius: 40 pixels (compact size for precise electrode marking)
- Stroke width: 6px (bold enough for visibility)
- Style: Single hollow circle (no fill, transparent center)
- **Note**: Rings provide clear electrode identification without being overwhelming

**Positioning**: Updated `montage_visualizer.py` for compact centered rings:
- Place ring image at (electrode_x - 50, electrode_y - 50)
- This centers each ring perfectly on electrode coordinates
- Single compact ring per electrode position

## Connection Lines Feature

**New Feature**: Arched connection lines between electrode pairs
- **Style**: Smooth quadratic Bezier curves creating natural arches
- **Color**: Matches the ring color for each electrode pair
- **Width**: 3px stroke for clear visibility
- **Arch Height**: 25% of the distance between electrodes for pleasing curves

**Algorithm**:
1. Calculate vector between electrode centers
2. Offset start/end points by 15px away from each electrode
3. Calculate midpoint between offset points
4. Create perpendicular vector for arching effect
5. Place control point at 25% of distance perpendicular to the line
6. Draw quadratic Bezier curve from offset start to offset end via control point

**Visual Result**: Each electrode pair is connected by elegant arched lines that start and end 15px away from electrode centers, creating clean visual channel representations that don't interfere with the ring markers.

## Dependencies

- Python 3.x
- ImageMagick (for image processing)
- `montage_visualizer.py` script

## Test Configuration

The test automatically:
- Detects local resources in the `amv/` directory
- Creates temporary montage configuration files
- Uses the GSN-256.png template for all visualizations
- Maps electrode coordinates from the appropriate CSV files

## Electrode Coordinates

### GSN-256 Network
- E010: (1203, 281)
- E011: (1130, 300)
- E012: (1062, 336)
- E013: (1012, 378)

### 10-10 Network
- Fp2: (1102, 228)
- AF8: (1204, 281)
- F10: (1427, 383)
- FT10: (1468, 529)

All coordinates are overlaid with colored rings on the GSN-256.png template image.
