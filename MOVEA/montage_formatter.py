"""
Format MOVEA optimization results for TI-Toolbox integration
"""

import numpy as np
import csv
from pathlib import Path
from datetime import datetime


class MontageFormatter:
    """Format and save MOVEA optimization results"""
    
    def __init__(self, electrode_coords_file=None):
        """
        Initialize formatter
        
        Args:
            electrode_coords_file: CSV file with electrode coordinates
        """
        self.electrode_coords = None
        self.electrode_names = []
        
        if electrode_coords_file:
            print(f"[MontageFormatter] Loading electrode names from: {electrode_coords_file}")
            self.load_electrode_coordinates(electrode_coords_file)
        else:
            print("[MontageFormatter] No electrode CSV file provided, using generic names (E0, E1, ...)")
    
    def load_electrode_coordinates(self, csv_file):
        """
        Load electrode coordinates and names from CSV
        
        Args:
            csv_file: CSV file with format: Type, X, Y, Z, Name
        """
        csv_file = Path(csv_file)
        if not csv_file.exists():
            print(f"Warning: Electrode coordinate file not found: {csv_file}")
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
                print(f"  Detected delimiter: {delim_name}")
                break
        
        self.electrode_coords = np.array(coords) if coords else None
        self.electrode_names = names
        
        if len(self.electrode_names) > 0:
            print(f"✓ Loaded {len(self.electrode_names)} electrode names from {csv_file.name}")
            print(f"  First few: {', '.join(self.electrode_names[:5])}")
        else:
            print(f"Warning: No electrodes loaded from {csv_file}")
    
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
        
        print(f"Montage saved to: {output_file}")
    
    def save_montage_simnibs(self, montage_dict, output_file):
        """
        Save montage in SimNIBS-compatible format
        
        Args:
            montage_dict: Formatted montage dictionary
            output_file: Output text file path
        """
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            f.write("# TI Montage - MOVEA Optimization\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Pair 1
            p1 = montage_dict['pair1']
            f.write(f"# Pair 1 (Frequency f1)\n")
            f.write(f"{p1['anode']['name']}\t{p1['current_mA']:.3f}\n")
            f.write(f"{p1['cathode']['name']}\t{-p1['current_mA']:.3f}\n\n")
            
            # Pair 2
            p2 = montage_dict['pair2']
            f.write(f"# Pair 2 (Frequency f2)\n")
            f.write(f"{p2['anode']['name']}\t{p2['current_mA']:.3f}\n")
            f.write(f"{p2['cathode']['name']}\t{-p2['current_mA']:.3f}\n\n")
            
            # Optimization info
            opt = montage_dict['optimization']
            f.write(f"# Optimization: {opt['method']}\n")
            f.write(f"# Field Strength: {opt['field_strength_V/m']:.6f} V/m\n")
        
        print(f"SimNIBS montage saved to: {output_file}")
    
    def print_montage(self, montage_dict):
        """Print montage to console"""
        print("\n" + "="*60)
        print("TI MONTAGE - MOVEA OPTIMIZATION")
        print("="*60)
        
        print("\nPair 1:")
        p1 = montage_dict['pair1']
        print(f"  Anode:   {p1['anode']['name']:8s} (#{p1['anode']['index']:2d})  +{p1['current_mA']:.1f} mA")
        print(f"  Cathode: {p1['cathode']['name']:8s} (#{p1['cathode']['index']:2d})  -{p1['current_mA']:.1f} mA")
        
        print("\nPair 2:")
        p2 = montage_dict['pair2']
        print(f"  Anode:   {p2['anode']['name']:8s} (#{p2['anode']['index']:2d})  +{p2['current_mA']:.1f} mA")
        print(f"  Cathode: {p2['cathode']['name']:8s} (#{p2['cathode']['index']:2d})  -{p2['current_mA']:.1f} mA")
        
        print("\nOptimization Results:")
        opt = montage_dict['optimization']
        print(f"  Method:         {opt['method']}")
        print(f"  Field Strength: {opt['field_strength_V/m']:.6f} V/m")
        print(f"  Cost:           {opt['cost']:.6f}")
        print(f"  Generations:    {opt['generations']}")
        print(f"  Population:     {opt['population']}")
        print("="*60 + "\n")


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
    if output_path.suffix.lower() == '.csv':
        formatter.save_montage_csv(montage, output_path)
    else:
        formatter.save_montage_simnibs(montage, output_path)
    
    formatter.print_montage(montage)
    
    return montage

