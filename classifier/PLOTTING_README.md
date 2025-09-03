# TI-Toolbox Classifier Plotting Module

This module provides comprehensive visualization capabilities for the TI-Toolbox Classifier, implementing plotting functions based on the methodology from Albizu et al. (2020).

## Overview

The plotting module (`core/plotting.py`) creates publication-quality visualizations that help interpret classifier results and understand the underlying patterns in TI stimulation data. All plots are automatically generated during the training process and saved in the `results/plots/` directory.

## Generated Visualizations

### 1. Performance Metrics (`performance_metrics.png/pdf`)

**Based on `plotPerf.m` from the original paper**

- **ROC Curves**: Receiver Operating Characteristic curves with confidence intervals
- **AUC Comparison**: Area Under the Curve comparison with statistical significance
- **Accuracy Distribution**: Cross-validation accuracy distribution across folds
- **Confusion Matrix**: Aggregate confusion matrix showing classification performance
- **Performance Summary**: Bar chart of key metrics (Accuracy, AUC)
- **CV Stability**: Cross-validation stability across folds

### 2. Weight Interpretation (`weight_interpretation.png/pdf`)

**Based on `interpretWeights.m` from the original paper**

- **Current Intensity Histogram**: Distribution of current intensities for responders vs non-responders
- **Cumulative Distribution**: Cumulative probability distributions
- **Logistic Regression**: Relationship between current intensity and response probability
- **Gardner-Altman Plot**: Effect size visualization with bootstrap confidence intervals
- **Weight Distribution**: Distribution of SVM feature weights
- **Current vs Response**: Scatter plot showing current intensity vs response relationship

### 3. ROI Ranking (`roi_ranking.png/pdf`)

**Brain region importance analysis**

- **Top 20 ROI Contributions**: Horizontal bar chart showing most important brain regions
- **Weight Distribution**: Distribution of ROI contributions across all regions
- **Color coding**: Green for responder-predictive, red for non-responder-predictive regions

### 4. Dosing Analysis (`dosing_analysis.png/pdf`)

**Based on `plotGroupDosing.m` from the original paper**

- **PCA Clustering**: Principal component analysis of current patterns
- **Current Magnitude Distribution**: Histograms comparing responder vs non-responder magnitudes
- **Dosing Variability**: Coefficient of variation analysis with statistical tests
- **Group Statistics**: Mean current density comparisons with error bars
- **Spatial Distribution**: Simplified spatial representation of current patterns
- **Effect Size Analysis**: Cohen's d distribution across voxels

## Technical Features

### Color Scheme
- **Responders**: Green (`[0.133, 0.545, 0.133]`)
- **Non-responders**: Red (`[0.635, 0.078, 0.184]`)
- **Combined/General**: Blue (`[0, 0.447, 0.741]`)
- **Chance level**: Black

### Font Sizes
- **Title**: 14pt, bold
- **Subtitles**: 12pt, bold
- **Labels**: 10pt, bold

### Output Formats
- **PNG**: High-resolution (300 DPI) for presentations and web
- **PDF**: Vector format for publications

## Usage

### Automatic Generation
Plots are automatically generated during classifier training:

```python
from ti_classifier import TIClassifier

classifier = TIClassifier(project_dir="path/to/project")
results = classifier.train("response_data.csv")
# Plots automatically saved to results/plots/
```

### Manual Generation
You can also generate plots manually:

```python
from core.plotting import TIClassifierPlotter

plotter = TIClassifierPlotter("output/directory")
plotter.create_all_plots(results, training_data)
plotter.create_summary_report(results, training_data)
```

### Example Script
Run the example script to see all plotting capabilities:

```bash
cd classifier/
python example_plotting.py
```

## Dependencies

The plotting module requires these additional packages (automatically installed with `requirements.txt`):

```
matplotlib>=3.5.0
seaborn>=0.11.0
scikit-learn>=1.1.0
scipy>=1.9.0
numpy>=1.21.0
pandas>=1.5.0
```

## Output Files

All plots are saved in the `results/plots/` directory:

```
results/
└── plots/
    ├── performance_metrics.png
    ├── performance_metrics.pdf
    ├── weight_interpretation.png
    ├── weight_interpretation.pdf
    ├── roi_ranking.png
    ├── roi_ranking.pdf
    ├── dosing_analysis.png
    ├── dosing_analysis.pdf
    └── classification_report.txt
```

## Summary Report

The `classification_report.txt` file provides a comprehensive text summary including:

- Model performance metrics
- Top 10 most important brain regions
- Training data summary
- List of generated visualization files

## Customization

The plotting module is designed to be extensible. You can:

1. **Modify colors**: Edit the `self.colors` dictionary in `TIClassifierPlotter`
2. **Add new plots**: Create new methods following the existing pattern
3. **Adjust styling**: Modify font sizes, figure sizes, or matplotlib style settings
4. **Export formats**: Add additional output formats as needed

## Scientific Background

These visualizations are based on the methodology described in:

**Albizu, A., Fang, R., Indahlastari, A., O'Shea, A., Stolte, S. E., See, K. B., ... & Woods, A. J. (2020).** Machine learning and individual variability in electric field characteristics predict tDCS treatment response. *Brain Stimulation*, 13(6), 1753-1764.

The plots help researchers and clinicians:

1. **Understand model performance** through comprehensive metrics
2. **Interpret biological significance** via weight analysis
3. **Identify important brain regions** for treatment response
4. **Analyze dosing patterns** and group differences
5. **Validate results** through multiple visualization perspectives

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure all dependencies are installed (`pip install -r requirements.txt`)
2. **Memory issues**: For large datasets, the plotting may require substantial RAM
3. **Display issues**: If running on a headless server, ensure matplotlib backend is set correctly

### Support

For questions or issues with the plotting functionality, please refer to the main TI-Toolbox documentation or create an issue in the project repository.
