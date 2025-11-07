"""
Format MOVEA optimization results for TI-Toolbox integration
"""

import numpy as np
import csv
from pathlib import Path
from datetime import datetime


class MontageFormatter:
    """Format and save MOVEA optimization results"""
    
    def __init__(self, electrode_coords_file=None, progress_callback=None):
        """
        Initialize formatter
        
        Args:
            electrode_coords_file: CSV file with electrode coordinates
            progress_callback: Optional callback function(message, type) for progress updates
        """
        self.electrode_coords = None
        self.electrode_names = []
        self._progress_callback = progress_callback
        
        if electrode_coords_file:
            self._log(f"Loading electrode names from: {electrode_coords_file}", 'info')
            self.load_electrode_coordinates(electrode_coords_file)
        else:
            self._log("No electrode CSV file provided, using generic names (E0, E1, ...)", 'info')
    
    def _log(self, message, msg_type='info'):
        """Send log message through callback or fallback to print"""
        if self._progress_callback:
            self._progress_callback(message, msg_type)
        else:
            print(message)
    
    def load_electrode_coordinates(self, csv_file):
        """
        Load electrode coordinates and names from CSV
        
        Args:
            csv_file: CSV file with format: Type, X, Y, Z, Name
        """
        csv_file = Path(csv_file)
        if not csv_file.exists():
            self._log(f"Warning: Electrode coordinate file not found: {csv_file}", 'warning')
            return
        
        coords = []
        names = []
        
        with open(csv_file, 'r') as f:
            # Read all lines first to detect delimiter
            lines = f.readlines()
            
        # Try to parse with different delimiters
        for delimiter in ['\t', ' ', ',']:
            coords = []
            names = []
            
            for line_num, line in enumerate(lines):
                if not line.strip():
                    continue
                    
                # Split by delimiter
                parts = [p.strip() for p in line.split(delimiter) if p.strip()]
                
                # Skip if not enough parts
                if len(parts) < 5:
                    continue
                
                # Check if this is an electrode row
                if parts[0] == 'Electrode':
                    try:
                        # parts: [Electrode, X, Y, Z, Name, ...]
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        name = parts[4]
                        coords.append([x, y, z])
                        names.append(name)
                    except (ValueError, IndexError) as e:
                        continue
            
            # If we found electrodes, we used the right delimiter
            if len(names) > 0:
                delim_name = 'tab' if delimiter == '\t' else 'space' if delimiter == ' ' else 'comma'
                self._log(f"  Detected delimiter: {delim_name}", 'info')
                break
        
        self.electrode_coords = np.array(coords) if coords else None
        self.electrode_names = names
        
        if len(self.electrode_names) > 0:
            self._log(f"✓ Loaded {len(self.electrode_names)} electrode names from {csv_file.name}", 'success')
            self._log(f"  First few: {', '.join(self.electrode_names[:5])}", 'info')
        else:
            self._log(f"Warning: No electrodes loaded from {csv_file}", 'warning')
    
    def format_ti_montage(self, optimization_result, current_mA=2.0):
        """
        Format TI montage from optimization result
        
        Args:
            optimization_result: Dictionary from TIOptimizer
            current_mA: Current magnitude in mA
        
        Returns:
            montage_dict: Formatted montage configuration
        """
        electrodes = optimization_result['electrodes']
        e1, e2, e3, e4 = electrodes
        
        montage = {
            'pair1': {
                'anode': self._get_electrode_info(e1),
                'cathode': self._get_electrode_info(e2),
                'current_mA': current_mA,
            },
            'pair2': {
                'anode': self._get_electrode_info(e3),
                'cathode': self._get_electrode_info(e4),
                'current_mA': current_mA,
            },
            'optimization': {
                'method': 'MOVEA',
                'field_strength_V/m': optimization_result.get('field_strength', 0),
                'cost': optimization_result.get('cost', 0),
                'generations': optimization_result.get('generations', 0),
                'population': optimization_result.get('population', 0),
            }
        }
        
        return montage
    
    def _get_electrode_info(self, electrode_idx):
        """Get electrode information by index"""
        info = {'index': int(electrode_idx)}
        
        if self.electrode_names and electrode_idx < len(self.electrode_names):
            info['name'] = self.electrode_names[electrode_idx]
        else:
            info['name'] = f"E{electrode_idx}"
        
        if self.electrode_coords is not None and electrode_idx < len(self.electrode_coords):
            coords = self.electrode_coords[electrode_idx]
            info['coordinates'] = {
                'x': float(coords[0]),
                'y': float(coords[1]),
                'z': float(coords[2])
            }
        
        return info
    
    def save_montage_csv(self, montage_dict, output_file):
        """
        Save montage to CSV file (TI-Toolbox format)
        
        Args:
            montage_dict: Formatted montage dictionary
            output_file: Output CSV file path
        """
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow(['TI Montage - MOVEA Optimization'])
            writer.writerow(['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow([])
            
            # Pair 1
            writer.writerow(['Pair 1'])
            p1 = montage_dict['pair1']
            writer.writerow([
                'Anode', 
                p1['anode']['name'], 
                p1['anode']['index'],
                f"{p1['current_mA']} mA"
            ])
            writer.writerow([
                'Cathode', 
                p1['cathode']['name'], 
                p1['cathode']['index'],
                f"-{p1['current_mA']} mA"
            ])
            writer.writerow([])
            
            # Pair 2
            writer.writerow(['Pair 2'])
            p2 = montage_dict['pair2']
            writer.writerow([
                'Anode', 
                p2['anode']['name'], 
                p2['anode']['index'],
                f"{p2['current_mA']} mA"
            ])
            writer.writerow([
                'Cathode', 
                p2['cathode']['name'], 
                p2['cathode']['index'],
                f"-{p2['current_mA']} mA"
            ])
            writer.writerow([])
            
            # Optimization info
            writer.writerow(['Optimization Results'])
            opt = montage_dict['optimization']
            writer.writerow(['Method', opt['method']])
            writer.writerow(['Field Strength (V/m)', f"{opt['field_strength_V/m']:.6f}"])
            writer.writerow(['Cost', f"{opt['cost']:.6f}"])
            writer.writerow(['Generations', opt['generations']])
            writer.writerow(['Population', opt['population']])
        
        self._log(f"Montage saved to: {output_file}", 'success')

    def print_montage(self, montage_dict):
        """Print montage to console"""
        self._log("\n" + "="*60, 'default')
        self._log("TI MONTAGE - MOVEA OPTIMIZATION", 'info')
        self._log("="*60, 'default')
        
        self._log("\nPair 1:", 'info')
        p1 = montage_dict['pair1']
        self._log(f"  Anode:   {p1['anode']['name']:8s} (#{p1['anode']['index']:2d})  +{p1['current_mA']:.1f} mA", 'default')
        self._log(f"  Cathode: {p1['cathode']['name']:8s} (#{p1['cathode']['index']:2d})  -{p1['current_mA']:.1f} mA", 'default')
        
        self._log("\nPair 2:", 'info')
        p2 = montage_dict['pair2']
        self._log(f"  Anode:   {p2['anode']['name']:8s} (#{p2['anode']['index']:2d})  +{p2['current_mA']:.1f} mA", 'default')
        self._log(f"  Cathode: {p2['cathode']['name']:8s} (#{p2['cathode']['index']:2d})  -{p2['current_mA']:.1f} mA", 'default')
        
        self._log("\nOptimization Results:", 'info')
        opt = montage_dict['optimization']
        self._log(f"  Method:         {opt['method']}", 'default')
        self._log(f"  Field Strength: {opt['field_strength_V/m']:.6f} V/m", 'default')
        self._log(f"  Cost:           {opt['cost']:.6f}", 'default')
        self._log(f"  Generations:    {opt['generations']}", 'default')
        self._log(f"  Population:     {opt['population']}", 'default')
        self._log("="*60 + "\n", 'default')


def quick_save(optimization_result, output_path, electrode_coords_file=None, current_mA=2.0):
    """
    Quick function to format and save optimization result
    
    Args:
        optimization_result: Dictionary from TIOptimizer
        output_path: Output file path (CSV or TXT)
        electrode_coords_file: Optional electrode coordinates CSV
        current_mA: Current magnitude in mA
    """
    formatter = MontageFormatter(electrode_coords_file)
    montage = formatter.format_ti_montage(optimization_result, current_mA)
    
    output_path = Path(output_path)
    # Always save as CSV format, regardless of file extension
    formatter.save_montage_csv(montage, output_path)
    
    formatter.print_montage(montage)
    
    return montage

