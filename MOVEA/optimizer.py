"""
TI electrode optimization using scipy's differential_evolution
"""

import numpy as np
from scipy.optimize import differential_evolution
from pathlib import Path
from .utils import calculate_ti_field, find_target_voxels, validate_ti_montage


class TIOptimizer:
    """TI electrode montage optimizer using scipy (no geatpy dependency)"""
    
    def __init__(self, leadfield_matrix, voxel_positions, num_electrodes=75):
        """
        Initialize TI optimizer with scipy backend
        
        Args:
            leadfield_matrix: Leadfield matrix [n_electrodes, n_voxels, 3]
            voxel_positions: Voxel MNI coordinates [n_voxels, 3]
            num_electrodes: Number of electrodes in cap
        """
        self.lfm = leadfield_matrix
        self.positions = voxel_positions
        self.num_electrodes = num_electrodes
        self.target_indices = None
        self.optimization_results = []
        self._eval_count = 0
    
    def set_target(self, target_mni, roi_radius_mm=10):
        """
        Set optimization target ROI
        
        Args:
            target_mni: Target MNI coordinate [x, y, z]
            roi_radius_mm: ROI radius in mm
        """
        self.target_indices = find_target_voxels(
            self.positions, target_mni, roi_radius_mm
        )
        if len(self.target_indices) == 0:
            raise ValueError(f"No voxels found within {roi_radius_mm}mm of target {target_mni}")
    
    def evaluate_montage(self, electrode_indices, current_ratio=0, return_dual_objective=False):
        """
        Evaluate a TI montage configuration
        
        Args:
            electrode_indices: [e1, e2, e3, e4] electrode indices
            current_ratio: Current ratio adjustment (optional)
            return_dual_objective: If True, return both objectives [intensity_cost, focality]
        
        Returns:
            cost: Single objective (intensity only) or tuple (intensity, focality)
        """
        # Convert to integers and validate
        electrode_indices = np.round(electrode_indices).astype(int)
        
        if not validate_ti_montage(electrode_indices):
            if return_dual_objective:
                return np.array([1000.0, 1000.0])
            return 1000.0
        
        e1, e2, e3, e4 = electrode_indices
        
        # Ensure indices are within bounds
        if np.any(electrode_indices >= self.num_electrodes) or np.any(electrode_indices < 0):
            if return_dual_objective:
                return np.array([1000.0, 1000.0])
            return 1000.0
        
        # Create stimulation patterns (bipolar pairs)
        stim1 = np.zeros(self.num_electrodes)
        stim1[e1] = 1 + current_ratio / self.num_electrodes
        stim1[e2] = -(1 + current_ratio / self.num_electrodes)
        
        stim2 = np.zeros(self.num_electrodes)
        stim2[e3] = 1 - current_ratio / self.num_electrodes
        stim2[e4] = -(1 - current_ratio / self.num_electrodes)
        
        if return_dual_objective:
            # Calculate full brain field for focality
            ti_field_full = calculate_ti_field(self.lfm, stim1, stim2, target_indices=None)
            ti_field_target = ti_field_full[self.target_indices]
            
            # Objective 1: Maximize target field (minimize reciprocal)
            avg_target = np.average(ti_field_target)
            obj1 = 1.0 / (avg_target + 1e-10)
            
            # Objective 2: Minimize whole brain field (focality)
            obj2 = np.mean(ti_field_full)
            
            return np.array([obj1, obj2])
        else:
            # Single objective: maximize target field only
            ti_field = calculate_ti_field(self.lfm, stim1, stim2, self.target_indices)
            avg_field = np.average(ti_field)
            cost = 1.0 / (avg_field + 1e-10)
            return cost
    
    def _objective_wrapper(self, x):
        """Wrapper for scipy optimizer (single objective)"""
        self._eval_count += 1
        if self._eval_count % 100 == 0:
            print(f"  Evaluations: {self._eval_count}")
        
        # x contains [e1, e2, e3, e4, current_ratio]
        return self.evaluate_montage(x[:4], current_ratio=x[4] if len(x) > 4 else 0, return_dual_objective=False)
    
    def optimize(self, max_generations=50, population_size=30, 
                 preset_target=None, roi_radius_mm=10, method='differential_evolution'):
        """
        Run scipy-based optimization
        
        Args:
            max_generations: Number of generations (iterations)
            population_size: Population size
            preset_target: Preset target name or MNI coordinate
            roi_radius_mm: ROI radius in mm
            method: Optimization method ('differential_evolution', 'dual_annealing', or 'basinhopping')
        
        Returns:
            best_solution: Dictionary with best electrode configuration
        """
        # Handle preset targets
        if preset_target is not None:
            target_mni = self._get_preset_target(preset_target)
            self.set_target(target_mni, roi_radius_mm)
        
        if self.target_indices is None:
            raise ValueError("Target not set. Call set_target() first.")
        
        # Calculate actual population for differential evolution
        if method == 'differential_evolution':
            popsize_multiplier = max(3, population_size // 5)
            actual_population = popsize_multiplier * 5
        else:
            actual_population = population_size
        
        print(f"\n{'='*60}")
        print(f"MOVEA Optimization - Scipy Backend")
        print(f"{'='*60}")
        print(f"Method: {method}")
        print(f"Target voxels: {len(self.target_indices)}")
        print(f"Max generations: {max_generations}")
        print(f"Requested population: {population_size}")
        if method == 'differential_evolution':
            print(f"Actual population: {actual_population} (popsize={popsize_multiplier} × 5 params)")
            print(f"Expected evaluations: ~{max_generations * actual_population}")
        print(f"{'='*60}\n")
        
        # Define bounds: 4 electrodes + 1 current ratio
        bounds = [(0, self.num_electrodes - 1)] * 4 + [(0, self.num_electrodes - 1)]
        
        self._eval_count = 0
        
        if method == 'differential_evolution':
            # Differential evolution is good for discrete optimization
            # popsize is a MULTIPLIER: actual_pop = popsize * num_params
            # For num_params=5, popsize=6 gives actual_pop=30
            popsize_multiplier = max(3, population_size // 5)  # Divide by number of parameters
            
            result = differential_evolution(
                self._objective_wrapper,
                bounds,
                maxiter=max_generations,
                popsize=popsize_multiplier,  # This is a multiplier!
                seed=42,
                workers=1,
                updating='deferred',
                atol=0.001,
                tol=0.001,
                polish=False  # Don't polish since we need integers
            )
        elif method == 'dual_annealing':
            from scipy.optimize import dual_annealing
            result = dual_annealing(
                self._objective_wrapper,
                bounds,
                maxiter=max_generations * population_size,
                seed=42
            )
        elif method == 'basinhopping':
            from scipy.optimize import basinhopping
            # Start with random initial guess
            x0 = np.random.randint(0, self.num_electrodes, 5)
            result = basinhopping(
                self._objective_wrapper,
                x0,
                niter=max_generations,
                seed=42
            )
        else:
            raise ValueError(f"Unknown method: {method}")
        
        # Extract best solution
        best_vars = np.round(result.x).astype(int)
        best_electrodes = best_vars[:4]
        best_cost = result.fun
        
        # Ensure valid solution
        best_electrodes = np.clip(best_electrodes, 0, self.num_electrodes - 1)
        
        solution = {
            'electrodes': best_electrodes.tolist(),
            'cost': float(best_cost),
            'field_strength': 1.0 / best_cost if best_cost > 0 else 0,
            'current_ratio': int(best_vars[4]) if len(best_vars) > 4 else 0,
            'generations': max_generations,
            'population': population_size,
            'method': method,
            'success': result.success if hasattr(result, 'success') else True,
            'evaluations': self._eval_count
        }
        
        self.optimization_results.append(solution)
        
        print(f"\n{'='*60}")
        print(f"Optimization Complete!")
        print(f"{'='*60}")
        print(f"Best electrodes: {solution['electrodes']}")
        print(f"Field strength: {solution['field_strength']:.6f} V/m")
        print(f"Cost: {solution['cost']:.4f}")
        print(f"Total evaluations: {self._eval_count}")
        print(f"Success: {solution['success']}")
        print(f"{'='*60}\n")
        
        return solution
    
    def generate_pareto_solutions(self, n_solutions=20, max_iter_per_solution=500):
        """
        Generate multiple Pareto-optimal solutions (like original MOVEA)
        Explores trade-off between intensity and focality
        
        Args:
            n_solutions: Number of solutions to generate
            max_iter_per_solution: Iterations per solution
        
        Returns:
            pareto_solutions: List of solution dictionaries with dual objectives
        """
        if self.target_indices is None:
            raise ValueError("Target not set. Call set_target() first.")
        
        print(f"\n{'='*60}")
        print(f"MOVEA Pareto Front Generation")
        print(f"{'='*60}")
        print(f"Target voxels: {len(self.target_indices)}")
        print(f"Generating {n_solutions} Pareto-optimal solutions")
        print(f"This explores intensity vs focality trade-offs")
        print(f"{'='*60}\n")
        
        pareto_solutions = []
        
        for i in range(n_solutions):
            if i % 5 == 0:
                print(f"Generating solution {i+1}/{n_solutions}...")
            
            # Use random search with dual objective evaluation
            best_cost = [float('inf'), float('inf')]
            best_electrodes = None
            best_cr = 0
            
            for _ in range(max_iter_per_solution):
                electrodes = np.random.choice(self.num_electrodes, size=4, replace=False)
                current_ratio = np.random.randint(0, self.num_electrodes)
                
                objs = self.evaluate_montage(electrodes, current_ratio, return_dual_objective=True)
                
                # Keep if better on intensity
                if objs[0] < best_cost[0]:
                    best_cost = objs.copy()
                    best_electrodes = electrodes.copy()
                    best_cr = current_ratio
            
            # Calculate actual field values
            intensity_field = 1.0 / best_cost[0] if best_cost[0] > 0 else 0
            focality = best_cost[1]
            
            solution = {
                'electrodes': best_electrodes.tolist(),
                'current_ratio': int(best_cr),
                'intensity_cost': float(best_cost[0]),
                'intensity_field': float(intensity_field),  # V/m at target
                'focality': float(focality),  # Whole brain field (V/m)
                'method': 'pareto_random_search'
            }
            
            pareto_solutions.append(solution)
        
        print(f"\n{'='*60}")
        print(f"Generated {len(pareto_solutions)} Pareto solutions")
        print(f"Intensity range: {min(s['intensity_field'] for s in pareto_solutions):.6f} - {max(s['intensity_field'] for s in pareto_solutions):.6f} V/m")
        print(f"Focality range: {min(s['focality'] for s in pareto_solutions):.6f} - {max(s['focality'] for s in pareto_solutions):.6f} V/m")
        print(f"{'='*60}\n")
        
        return pareto_solutions
    
    def optimize_simple(self, preset_target=None, roi_radius_mm=10, max_iter=1000):
        """
        Simple brute-force optimization with random sampling
        Fast but less optimal, good for quick tests
        
        Args:
            preset_target: Preset target name or MNI coordinate
            roi_radius_mm: ROI radius in mm
            max_iter: Maximum iterations
        
        Returns:
            best_solution: Dictionary with best electrode configuration
        """
        # Handle preset targets
        if preset_target is not None:
            target_mni = self._get_preset_target(preset_target)
            self.set_target(target_mni, roi_radius_mm)
        
        if self.target_indices is None:
            raise ValueError("Target not set. Call set_target() first.")
        
        print(f"Starting simple random search optimization...")
        print(f"Target voxels: {len(self.target_indices)}")
        print(f"Max iterations: {max_iter}")
        
        best_cost = float('inf')
        best_electrodes = None
        best_current_ratio = 0
        
        for i in range(max_iter):
            # Generate random unique electrode indices
            electrodes = np.random.choice(self.num_electrodes, size=4, replace=False)
            current_ratio = np.random.randint(0, self.num_electrodes)
            
            cost = self.evaluate_montage(electrodes, current_ratio)
            
            if cost < best_cost:
                best_cost = cost
                best_electrodes = electrodes.copy()
                best_current_ratio = current_ratio
                print(f"  Iteration {i+1}: New best cost = {best_cost:.6f}, electrodes = {best_electrodes}")
        
        solution = {
            'electrodes': best_electrodes.tolist(),
            'cost': float(best_cost),
            'field_strength': 1.0 / best_cost if best_cost > 0 else 0,
            'current_ratio': int(best_current_ratio),
            'iterations': max_iter,
            'method': 'random_search'
        }
        
        self.optimization_results.append(solution)
        
        print(f"\nOptimization complete!")
        print(f"Best electrodes: {solution['electrodes']}")
        print(f"Field strength: {solution['field_strength']:.6f} V/m")
        
        return solution
    
    def _get_preset_target(self, target_name):
        """Get MNI coordinates for preset targets"""
        presets = {
            'motor': np.array([47, -13, 52]),
            'dlpfc': np.array([-39, 34, 37]),
            'hippocampus': np.array([-31, -20, -14]),
            'hippo': np.array([-31, -20, -14]),
            'v1': np.array([10, -92, 2]),
            'thalamus': np.array([10, -19, 6]),
            'pallidum': np.array([-17, 3, -1]),
            'sensory': np.array([41, -36, 66]),
            'dorsal': np.array([25, 42, 37]),
        }
        
        if isinstance(target_name, str):
            target_name = target_name.lower()
            if target_name in presets:
                return presets[target_name]
            else:
                # Try to parse as coordinates
                try:
                    coords = [float(x) for x in target_name.split(',')]
                    if len(coords) == 3:
                        return np.array(coords)
                except:
                    pass
                raise ValueError(
                    f"Unknown target: {target_name}. "
                    f"Available: {list(presets.keys())} or 'x,y,z' coordinates"
                )
        else:
            return np.array(target_name)
