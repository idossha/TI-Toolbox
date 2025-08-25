# TI-Toolbox Analysis System

A streamlined, configuration-driven analysis system for TI-Toolbox research that can be easily shared with other developers.

## 🚀 Quick Start

### 1. Setup (One-time)
```bash
# Navigate to analysis directory
cd case_studies/analysis

# Run setup script (Unix/Mac)
./setup.sh

# OR for Windows
setup.bat
```

### 2. Activate Environment
```bash
# Unix/Mac
source ../../venv/bin/activate

# Windows
../../venv/Scripts/activate.bat
```

### 3. Run Analysis
```bash
# Complete analysis (all regions and all questions)
python main.py

# Specific region analysis
python main.py --region Left_Insula --optimization max

# Show help
python main.py --help
```

## 📁 File Structure

```
case_studies/analysis/
├── 📄 main.py                     # Main entry point
├── 📄 pipeline.py                 # Analysis pipeline orchestration
├── 📄 config.py                   # Configuration management
├── 📄 data.py                     # Data loading utilities
├── 📄 stats.py                    # Statistical functions (all research questions)
├── 📄 plots.py                    # Plotting utilities
├── ⚙️ settings.yaml               # Main configuration
├── ⚙️ example_settings.yaml       # Example configuration
├── 🛠️ setup.sh                    # Unix/Mac setup script
└── 🛠️ setup.bat                   # Windows setup script
```

## 🔬 Research Questions

### Q3: Demographic Factors (Comprehensive)
Analyzes correlations between demographic factors (age, bone characteristics) and electric field measures in regions of interest across all three conditions (ernie, mapped, optimized).

**Default Analysis**: The standard Q3 analysis now includes comprehensive correlation and regression analysis showing all three conditions on the same plot.

**Features:**
- **Comprehensive Correlation Plots**: Shows all three conditions (ernie, mapped, optimized) on the same subplot with correlation coefficients and p-values in the legend
- **Comprehensive Regression Plots**: Two-panel comparison showing R² values and regression coefficients across all mapping types
- **Enhanced Statistical Analysis**: Detailed analysis across all three conditions simultaneously



### Pairwise Comparisons
Performs statistical comparisons between different conditions:
- ernie vs mapped
- ernie vs optimized
- mapped vs optimized

## 🎯 Available Regions

| Region | Optimization Types | Description |
|--------|-------------------|-------------|
| Left_Insula | max, normal | Left Insula region |
| Right_Hippocampus | max | Right Hippocampus region |
| sphere_x36.10_y14.14_z0.33_r5 | max | Spherical target (36.10, 14.14, 0.33) with radius 5mm |

## ⚙️ Configuration

The `settings.yaml` file controls all aspects of the analysis:

### Analysis Settings
```yaml
analysis:
  questions:
    - "Q3"           # Demographic factors analysis
    - "pairwise"     # Pairwise comparisons
  save_results: true
  save_plots: true
```

### Data Settings
```yaml
data:
  regions:
    - name: "Left_Insula"
      optimization_types: ["max", "normal"]
    - name: "Right_Hippocampus"
      optimization_types: ["max"]
  conditions:
    - "ernie"
    - "mapped"
    - "optimized"
```

### Pipeline Settings
```yaml
pipeline:
  run_all_regions: true  # Run all regions by default
  default:
    region: "Left_Insula"
    optimization_type: "max"
```

## 📊 Output

### Results Files
- JSON files with complete analysis results
- Summary reports in text format
- Located in `../results/tables/`

### Figures
- Publication-quality plots
- Comparison visualizations
- Normality check plots
- Located in `../results/figures/`

### Logs
- Analysis logs with timestamps
- Located in `analysis.log`

## 🖥️ Command Line Options

```bash
python main.py [OPTIONS]

Options:
  --config, -c CONFIG_FILE     Path to configuration file (default: settings.yaml)
  --region, -r REGION          Target region to analyze
  --optimization, -o OPT_TYPE  Optimization type to analyze
  --all-regions, -a            Run analysis for all regions and optimization types
  --questions, -q [Q3|pairwise]  Specific research questions to run
  --validate-only              Only validate configuration and data availability
  --help                       Show help message
```

## 📋 Usage Examples

### Complete Analysis
```bash
python main.py
```
Runs analysis for all regions and optimization types with all research questions.

### Specific Region Analysis
```bash
python main.py --region Left_Insula --optimization max
```
Runs analysis for a specific region and optimization type.

### Specific Research Questions
```bash
python main.py --region Right_Hippocampus --optimization max --questions Q3
```
Runs only Q3 analysis for Right_Hippocampus with max optimization.

### Custom Configuration
```bash
python main.py --config custom_settings.yaml
```
Uses custom configuration file.

## 🔧 Customization

### Adding New Regions
Edit `settings.yaml`:
```yaml
data:
  regions:
    - name: "New_Region"
      optimization_types: ["max", "normal"]
      description: "Description of the new region"
```

### Modifying Analysis Settings
```yaml
analysis:
  questions:
    - "Q3"  # Only run Q3 analysis
  save_results: true
  save_plots: false  # Don't save plots
```

### Statistical Settings
```yaml
statistics:
  alpha: 0.01  # More stringent significance level
  effect_size:
    small: 0.05
    medium: 0.25
    large: 0.4
```

## 🛠️ Troubleshooting

### Common Issues

1. **Configuration file not found**
   - Ensure `settings.yaml` exists in the analysis directory
   - Check file permissions

2. **Data files not found**
   - Verify data files exist in `data/processed/`
   - Check file naming convention matches configuration

3. **Missing dependencies**
   - Install required packages: `pip install -r requirements.txt`
   - Ensure all analysis scripts are in the same directory

4. **Permission errors**
   - Check write permissions for output directories
   - Ensure Python has access to all required directories

### Validation
```bash
python main.py --validate-only
```
This checks:
- Configuration file validity
- Data file availability
- Output directory permissions

## 📚 Development

### Adding New Research Questions
1. Create analysis function in appropriate script
2. Add question name to configuration validation
3. Update analysis runner to handle new question
4. Update command line interface

### Modifying Analysis Logic
The core analysis logic remains in the original scripts:
- `demographic_analysis.py` - Q3 demographic analysis
- `pairwise_comparisons.py` - Comparison analysis
- `stats.py` - Statistical functions
- `plots.py` - Plotting functions

### Extending Configuration
To add new configuration options:
1. Add to `settings.yaml`
2. Update `ConfigLoader` class in `config.py`
3. Add validation in `validate_config()` method
4. Use in `pipeline.py` as needed

## 🔄 Backward Compatibility

All original functionality is preserved:
- Same statistical analyses
- Same plotting functions
- Same data loading logic
- Same output formats

The only changes are:
- Centralized configuration management
- Simplified command-line interface
- Better error handling and logging
- Improved validation and documentation

## 🎓 Academic Standards

The system follows academic and research best practices:
- **Descriptive naming**: Files clearly indicate functionality
- **Consistent conventions**: Follows established naming patterns
- **Professional appearance**: Suitable for research publications
- **Accessible design**: Clear to both technical and non-technical users

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Validate your configuration and data
3. Review the original analysis scripts for specific functionality
4. Check the analysis logs for detailed error messages 