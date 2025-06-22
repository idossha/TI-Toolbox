# Ex-Search System Updates

## Recent Improvements (October 31, 2024)

### 🚀 **TI Simulation Enhancements**

#### **Default 1mA Current**
- **ti_sim.py** now defaults to 1mA (0.001A) stimulation current
- Press Enter to accept default, or specify custom current in mA
- Proper current amplitude for TI stimulations

#### **Parallel Processing**
- **ti_sim.py** now includes built-in parallel processing
- Automatically detects available CPU cores
- Default: Uses up to 8 cores for optimal performance
- Reduces simulation time significantly for multiple electrode combinations
- Real-time progress tracking with ETA estimation

### 🐍 **Python Mesh Analysis**

#### **MATLAB Replacement**
- **mesh_field_analyzer.py** - Pure Python replacement for MATLAB field-analysis
- **run_python_mesh_analysis.py** - Wrapper script replacing shell/MATLAB executables
- No more MATLAB Runtime dependency
- Faster and more reliable processing

#### **Same Output Format**
- Generates identical `summary.csv` format
- Compatible with existing `update_output_csv.py`
- Maintains all field metrics: percentiles, focality, XYZ coordinates

### 🔧 **Integration Updates**

#### **CLI Integration**
- `CLI/ex-search.sh` updated to use new parallel simulation and Python analysis
- Seamless drop-in replacement

#### **GUI Integration** 
- `GUI/ex_search_tab.py` updated to use parallel processing
- Default 1mA current in GUI workflow
- Python mesh analysis integration

## 📊 **Performance Benefits**

- **Parallel TI Simulations**: 3-8x faster depending on core count
- **Python Analysis**: No MATLAB startup overhead, more reliable
- **Better Error Handling**: More informative error messages
- **Progress Tracking**: Real-time ETA and completion status

## 🔄 **Migration**

**No changes needed** - everything works automatically:
- Existing workflows use new parallel processing
- Same user interface and command-line arguments
- Output formats unchanged
- All dependencies are Python-based

## 📦 **Requirements**

### Python Dependencies (added)
```bash
pip install -r ex-search/requirements-python-analysis.txt
```
- meshio (for .msh file reading)
- numpy, pandas, matplotlib (for analysis)

### Removed Dependencies
- MATLAB Runtime (no longer needed)
- Compiled MATLAB executables 