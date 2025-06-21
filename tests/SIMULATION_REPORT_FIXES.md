# Simulation Report Generation Fixes

## Summary
Fixed multiple issues with the simulation report generation in the GUI that were causing errors when trying to generate reports after simulations completed.

## Issues Fixed

### 1. **Parameter Mismatch in GUI**
- **Problem**: The GUI was calling `add_simulation_parameters()` with positional arguments, but the method expects keyword arguments.
- **Fix**: Updated GUI to use keyword arguments:
  ```python
  self.report_generator.add_simulation_parameters(
      conductivity_type=conductivity,
      simulation_mode=sim_mode,
      eeg_net=eeg_net,
      intensity_ch1=current_ma_1,
      intensity_ch2=current_ma_2,
      quiet_mode=False,
      conductivities=self._get_conductivities_for_report()
  )
  ```

### 2. **Electrode Parameters Issue**
- **Problem**: The GUI was calling `add_electrode_parameters()` with positional arguments.
- **Fix**: Updated to use keyword arguments:
  ```python
  self.report_generator.add_electrode_parameters(
      shape=electrode_shape,
      dimensions=[float(dim_parts[0]), float(dim_parts[1])],
      thickness=float(thickness)
  )
  ```

### 3. **Extra Fields in Parameter Dictionaries**
- **Problem**: When copying parameters between report generators, extra calculated fields (like `area_mm2`, `timestamp`) were causing "unexpected keyword argument" errors.
- **Fix**: Only pass the expected parameters:
  ```python
  # For electrode parameters
  single_sim_generator.add_electrode_parameters(
      shape=electrode_params['shape'],
      dimensions=electrode_params['dimensions'],
      thickness=electrode_params['thickness']
  )
  
  # For montage parameters
  single_sim_generator.add_montage(
      name=montage['name'],
      electrode_pairs=montage.get('electrode_pairs', []),
      montage_type=montage.get('type', 'unipolar')
  )
  ```

### 4. **Intensity Parameter Names**
- **Problem**: The report generator stores intensity values as `intensity_ch1_ma` and `intensity_ch2_ma`, but the GUI was trying to access them as `intensity_ch1` and `intensity_ch2`.
- **Fix**: Updated to use the correct field names:
  ```python
  'intensity_ch1': float(params.get('intensity_ch1_ma') or 2.0),
  'intensity_ch2': float(params.get('intensity_ch2_ma') or 2.0),
  ```

### 5. **Montage Removal Fix**
- **Problem**: The montage removal functionality was trying to get the montage name from `text()` which included HTML formatting.
- **Fix**: Get the montage name from the UserRole data:
  ```python
  montage_name = selected_items[0].data(QtCore.Qt.UserRole)
  ```

## Files Modified

1. **GUI/simulator_tab.py**
   - Fixed parameter passing to report generator methods
   - Fixed montage removal functionality
   - Added proper error handling for report generation

2. **utils/simulation_report_generator.py**
   - Fixed montage image path to use correct filename pattern
   - Simplified T1 file finding to only look in m2m directory
   - Updated NIfTI file selection to prioritize subject space files
   - Added handling for 4D NIfTI arrays and dimension mismatches

3. **CLI/simulator.sh**
   - Added missing closing brace for the `run_simulation` function

## Testing

Created test scripts to verify the fixes:
- `tests/test_report_generation.py` - Tests report generation with example data
- `tests/test_gui_simulation_report.py` - Tests the GUI-style report generation
- `tests/test_gui_simulation_flow.py` - Tests the complete GUI simulation flow

All tests now pass successfully and reports are generated without errors. 