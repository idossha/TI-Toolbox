"""
TI electrode optimization using scipy's differential_evolution
"""

import numpy as np
from scipy.optimize import differential_evolution
from pathlib import Path
from .utils import calculate_ti_field, find_target_voxels, validate_ti_montage
import multiprocessing as mp
from functools import partial


def _worker_test():
    """Simple test function to verify workers are operational"""
    return "OK"


def _generate_single_pareto_solution(args):
    """
    Worker function for parallel Pareto solution generation
    
    Args:
        args: Tuple of (solution_idx, lfm, num_electrodes, target_indices, max_iter, seed)
    
    Returns:
        solution: Dictionary with Pareto solution
    """
    import time
    try:
        solution_idx, lfm, num_electrodes, target_indices, max_iter, seed = args
        start_time = time.time()
        
        # Set random seed for reproducibility
        np.random.seed(seed + solution_idx)
        
        best_cost = [float('inf'), float('inf')]
        best_electrodes = None
        best_cr = 0
        improvements = 0
        
        for iter_idx in range(max_iter):
            electrodes = np.random.choice(num_electrodes, size=4, replace=False)
            current_ratio = np.random.randint(0, 101)  # 0-100 for current ratio percentage
            
            # Evaluate dual objective
            objs = _evaluate_montage_dual(lfm, num_electrodes, target_indices, electrodes, current_ratio)
            
            # Keep if better on intensity
            if objs[0] < best_cost[0]:
                best_cost = objs.copy()
                best_electrodes = electrodes.copy()
                best_cr = current_ratio
                improvements += 1
        
        # Calculate actual field values
        intensity_field = 1.0 / best_cost[0] if best_cost[0] > 0 else 0
        focality = best_cost[1]
        elapsed = time.time() - start_time
        
        solution = {
            'electrodes': best_electrodes.tolist(),
            'current_ratio': int(best_cr),
            'intensity_cost': float(best_cost[0]),
            'intensity_field': float(intensity_field),  # V/m at target
            'focality': float(focality),  # Whole brain field (V/m)
            'method': 'pareto_random_search_parallel',
            'improvements': improvements,
            'time_seconds': elapsed,
            'solution_idx': solution_idx
        }
        
        return solution
    except Exception as e:
        import traceback
        # Return error result instead of crashing
        return {
            'electrodes': [0, 1, 2, 3],
            'current_ratio': 50,
            'intensity_cost': float('inf'),
            'intensity_field': 0.0,
            'focality': float('inf'),
            'method': 'pareto_error',
            'error': str(e),
            'traceback': traceback.format_exc(),
            'solution_idx': solution_idx
        }


def _evaluate_montage_dual(lfm, num_electrodes, target_indices, electrode_indices, current_ratio=0):
    """
    Static evaluation function for multiprocessing
    
    Args:
        lfm: Leadfield matrix
        num_electrodes: Number of electrodes
        target_indices: Target voxel indices
        electrode_indices: [e1, e2, e3, e4]
        current_ratio: Current ratio adjustment
    
    Returns:
        array: [intensity_cost, focality]
    """
    # Convert to integers and validate
    electrode_indices = np.round(electrode_indices).astype(int)
    
    if not validate_ti_montage(electrode_indices):
        return np.array([1000.0, 1000.0])
    
    e1, e2, e3, e4 = electrode_indices
    
    # Ensure indices are within bounds
    if np.any(electrode_indices >= num_electrodes) or np.any(electrode_indices < 0):
        return np.array([1000.0, 1000.0])
    
    # Create stimulation patterns (bipolar pairs)
    stim1 = np.zeros(num_electrodes)
    stim1[e1] = 1 + current_ratio / num_electrodes
    stim1[e2] = -(1 + current_ratio / num_electrodes)
    
    stim2 = np.zeros(num_electrodes)
    stim2[e3] = 1 - current_ratio / num_electrodes
    stim2[e4] = -(1 - current_ratio / num_electrodes)
    
    # Calculate full brain field for focality
    # WARNING: This can be very slow with millions of voxels (2.3M in this case)
    # Each evaluation computes E-field for ALL voxels, then TI envelope
    ti_field_full = calculate_ti_field(lfm, stim1, stim2, target_indices=None)
    ti_field_target = ti_field_full[target_indices]
    
    # Objective 1: Maximize target field (minimize reciprocal)
    avg_target = np.average(ti_field_target)
    obj1 = 1.0 / (avg_target + 1e-10)
    
    # Objective 2: Minimize whole brain field (focality)
    obj2 = np.mean(ti_field_full)
    
    return np.array([obj1, obj2])


class TIOptimizer:
    """TI electrode montage optimizer using scipy (no geatpy dependency)"""
    
    def __init__(self, leadfield_matrix, voxel_positions, num_electrodes=75, progress_callback=None):
        """
        Initialize TI optimizer with scipy backend
        
        Args:
            leadfield_matrix: Leadfield matrix [n_electrodes, n_voxels, 3]
            voxel_positions: Voxel MNI coordinates [n_voxels, 3]
            num_electrodes: Number of electrodes in cap
            progress_callback: Optional callback function(message, type) for progress updates
        """
        self.lfm = leadfield_matrix
        self.positions = voxel_positions
        self.num_electrodes = num_electrodes
        self.target_indices = None
        self.optimization_results = []
        self._eval_count = 0
        self._progress_callback = progress_callback
    
    def _log(self, message, msg_type='info'):
        """Send log message through callback or fallback to print"""
        if self._progress_callback:
            self._progress_callback(message, msg_type)
        else:
            print(message)
    
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
            self._log(f"  Evaluations: {self._eval_count}", 'info')
        
        # x contains [e1, e2, e3, e4, current_ratio]
        return self.evaluate_montage(x[:4], current_ratio=x[4] if len(x) > 4 else 0, return_dual_objective=False)
    
    def optimize(self, max_generations=500, population_size=30, 
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
        
        self._log(f"\n{'='*60}", 'default')
        self._log(f"MOVEA Optimization - Scipy Backend", 'info')
        self._log(f"{'='*60}", 'default')
        self._log(f"Method: {method}", 'info')
        self._log(f"Target voxels: {len(self.target_indices)}", 'info')
        self._log(f"Max generations: {max_generations}", 'info')
        self._log(f"Requested population: {population_size}", 'info')
        if method == 'differential_evolution':
            self._log(f"Actual population: {actual_population} (popsize={popsize_multiplier} × 5 params)", 'info')
            self._log(f"Expected evaluations: ~{max_generations * actual_population}", 'info')
        self._log(f"{'='*60}\n", 'default')
        
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
        
        self._log(f"\n{'='*60}", 'default')
        self._log(f"Optimization Complete!", 'success')
        self._log(f"{'='*60}", 'default')
        self._log(f"Best electrodes: {solution['electrodes']}", 'info')
        self._log(f"Field strength: {solution['field_strength']:.6f} V/m", 'info')
        self._log(f"Cost: {solution['cost']:.4f}", 'info')
        self._log(f"Total evaluations: {self._eval_count}", 'info')
        self._log(f"Success: {solution['success']}", 'info')
        self._log(f"{'='*60}\n", 'default')
        
        return solution
    
    def generate_pareto_solutions(self, n_solutions=20, max_iter_per_solution=500, n_cores=None):
        """
        Generate multiple Pareto-optimal solutions (like original MOVEA) with multi-core parallelization
        Explores trade-off between intensity and focality
        
        Args:
            n_solutions: Number of solutions to generate
            max_iter_per_solution: Iterations per solution
            n_cores: Number of CPU cores to use (None = auto-detect, 1 = serial)
        
        Returns:
            pareto_solutions: List of solution dictionaries with dual objectives
        """
        if self.target_indices is None:
            raise ValueError("Target not set. Call set_target() first.")
        
        # Determine number of cores
        if n_cores is None:
            n_cores = max(1, mp.cpu_count() - 1)  # Leave one core free
        elif n_cores <= 0:
            n_cores = mp.cpu_count()
        
        use_parallel = n_cores > 1 and n_solutions > 1
        
        # Check for very large leadfields
        n_voxels = self.lfm.shape[1]
        total_evaluations = n_solutions * max_iter_per_solution
        
        self._log(f"\n{'='*60}", 'default')
        self._log(f"MOVEA Pareto Front Generation", 'info')
        self._log(f"{'='*60}", 'default')
        self._log(f"Leadfield size: {n_voxels:,} voxels", 'info')
        self._log(f"Target voxels: {len(self.target_indices)}", 'info')
        self._log(f"Generating {n_solutions} Pareto-optimal solutions", 'info')
        self._log(f"Iterations per solution: {max_iter_per_solution}", 'info')
        self._log(f"Total evaluations: {total_evaluations:,}", 'info')
        
        # Warning for large computations
        if n_voxels > 500000:  # More than 500k voxels
            # Estimate memory usage per worker
            lfm_size_mb = (self.lfm.nbytes) / (1024 * 1024)
            total_memory_mb = lfm_size_mb * n_cores
            
            self._log("", 'default')
            self._log("⚠ WARNING: Large leadfield detected!", 'warning')
            self._log(f"  Leadfield size: {lfm_size_mb:.1f} MB per worker", 'warning')
            self._log(f"  Total memory for {n_cores} workers: ~{total_memory_mb:.1f} MB", 'warning')
            self._log(f"  {n_voxels:,} voxels × {total_evaluations:,} evaluations", 'warning')
            self._log(f"  Each evaluation computes TI field for ALL voxels", 'warning')
            self._log(f"  This will be VERY SLOW (minutes to hours)", 'warning')
            
            if total_memory_mb > 16000:  # More than 16GB
                self._log(f"  ⚠⚠ Memory usage may cause system instability!", 'warning')
            
            self._log("  Consider:", 'warning')
            self._log(f"    • Reducing solutions to 5-10", 'warning')
            self._log(f"    • Reducing iterations to 50-100", 'warning')
            self._log(f"    • Reducing CPU cores to 4-6", 'warning')
            self._log(f"    • Or skip Pareto generation entirely", 'warning')
            self._log("", 'default')
        
        if use_parallel:
            self._log(f"Using {n_cores} CPU cores in parallel", 'info')
        else:
            self._log(f"Using serial processing (1 core)", 'info')
        self._log(f"This explores intensity vs focality trade-offs", 'info')
        self._log(f"{'='*60}\n", 'default')
        
        if use_parallel:
            # Parallel processing with multiprocessing
            # Prepare arguments for each worker
            worker_args = [
                (i, self.lfm, self.num_electrodes, self.target_indices, max_iter_per_solution, 42)
                for i in range(n_solutions)
            ]
            
            # Estimate realistic timeout based on problem size
            # Pareto uses FULL brain field, not just target
            n_voxels_full = self.lfm.shape[1]
            n_target_voxels = len(self.target_indices)
            
            # Base estimate on single-objective performance
            # Assume each full-brain evaluation takes proportionally longer than target-only
            # Rough estimate: 0.05s per 10k voxels (conservative)
            eval_time_estimate = (n_voxels_full / 10000) * 0.05  # seconds per evaluation
            total_time_estimate = (n_solutions * max_iter_per_solution * eval_time_estimate) / n_cores
            
            # Add large buffer for safety and ensure reasonable minimum
            timeout_seconds = max(1800, int(total_time_estimate * 3.0))  # At least 30 min
            
            # Cap at reasonable maximum (4 hours)
            timeout_seconds = min(timeout_seconds, 14400)
            
            self._log("Starting parallel processing...", 'info')
            self._log(f"Estimated time: {int(total_time_estimate/60)} min, timeout: {int(timeout_seconds/60)} min", 'info')
            
            pareto_solutions = []
            pool = None  # Initialize to None for finally block
            
            try:
                # Set start method to 'fork' on Unix for better performance/reliability
                import sys
                import time
                
                if sys.platform != 'win32':
                    try:
                        mp.set_start_method('fork', force=True)
                    except RuntimeError:
                        pass  # Already set
                
                self._log(f"Creating worker pool with {n_cores} processes...", 'info')
                pool = mp.Pool(processes=n_cores)
                
                try:
                    self._log(f"  Worker pool created", 'info')
                    
                    # Test that workers are actually running with a simple task
                    self._log("  Testing workers...", 'info')
                    test_result = pool.apply_async(_worker_test)
                    try:
                        test_msg = test_result.get(timeout=10)
                        self._log(f"  ✓ Workers responding: {test_msg}", 'success')
                    except mp.TimeoutError:
                        self._log(f"  ✗ Workers not responding after 10s - aborting", 'error')
                        self._log(f"  This may indicate memory issues or worker crashes", 'error')
                        pool.terminate()
                        pool.join()
                        pareto_solutions = []
                        return []
                    except Exception as test_err:
                        self._log(f"  ✗ Worker test failed: {str(test_err)}", 'error')
                        import traceback
                        self._log(f"  {traceback.format_exc()}", 'debug')
                        pool.terminate()
                        pool.join()
                        pareto_solutions = []
                        return []
                    
                    # Use map_async instead of imap to avoid blocking forever
                    self._log("  Submitting work to pool...", 'info')
                    result_async = pool.map_async(_generate_single_pareto_solution, worker_args)
                    self._log("  Work submitted, monitoring progress...", 'info')
                    
                    # Monitor progress without blocking
                    start_time = time.time()
                    last_log_time = start_time
                    
                    self._log("", 'default')
                    
                    while True:
                        current_time = time.time()
                        elapsed = current_time - start_time
                        
                        # Check if results are ready (non-blocking)
                        if result_async.ready():
                            self._log(f"  All workers completed after {int(elapsed)}s ({int(elapsed/60)}min)", 'success')
                            break
                        
                        # Check timeout
                        if elapsed > timeout_seconds:
                            self._log(f"  ⚠ Timeout after {int(elapsed)}s ({int(elapsed/60)} min) - terminating workers", 'warning')
                            pool.terminate()
                            pool.join()
                            pareto_solutions = []
                            break
                        
                        # Log progress every 10 seconds
                        if current_time - last_log_time >= 10:
                            self._log(
                                f"  Processing... Elapsed: {int(elapsed/60)}m:{int(elapsed%60):02d}s | "
                                f"Timeout in: {int((timeout_seconds - elapsed)/60)}m",
                                'info'
                            )
                            last_log_time = current_time
                        
                        # Wait a bit before checking again (non-blocking)
                        result_async.wait(timeout=2)
                    
                    # Get results if computation completed
                    if result_async.ready():
                        self._log("  Collecting results...", 'info')
                        try:
                            completed_solutions = result_async.get(timeout=30)
                            total_time = time.time() - start_time
                            
                            self._log("", 'default')
                            self._log(f"  ✓ Collection complete: {len(completed_solutions)}/{n_solutions} solutions in {int(total_time)}s ({int(total_time/60)}min)", 'success')
                            
                            # Log some solution statistics
                            if completed_solutions:
                                for idx, sol in enumerate(completed_solutions[:5]):  # Show first 5
                                    if sol.get('method') != 'pareto_error':
                                        self._log(
                                            f"    Sol {idx+1}: I={sol['intensity_field']:.4f} V/m, "
                                            f"F={sol['focality']:.4f} V/m, "
                                            f"time={sol.get('time_seconds', 0):.1f}s",
                                            'info'
                                        )
                            
                            pareto_solutions = completed_solutions
                            
                        except Exception as e:
                            self._log(f"  Error collecting results: {str(e)}", 'error')
                            import traceback
                            self._log(f"  {traceback.format_exc()}", 'debug')
                            pareto_solutions = []
                
                finally:
                    # Always clean up pool
                    if pool is not None:
                        self._log("  Closing worker pool...", 'info')
                        pool.close()
                        pool.join()
                        self._log("  Worker pool closed", 'info')
                    
            except KeyboardInterrupt:
                self._log("  User interrupted - terminating workers...", 'warning')
                if pool is not None:
                    try:
                        pool.terminate()
                        pool.join()
                    except:
                        pass
                pareto_solutions = []
            except Exception as e:
                self._log(f"  Critical error in parallel processing: {str(e)}", 'error')
                import traceback
                self._log(f"  {traceback.format_exc()}", 'debug')
                if pool is not None:
                    try:
                        pool.terminate()
                        pool.join()
                    except:
                        pass
                pareto_solutions = []
            
            if pareto_solutions and len(pareto_solutions) > 0:
                self._log("", 'default')
                self._log("Validating and filtering solutions...", 'info')
                
                # Filter out any error results
                valid_solutions = [s for s in pareto_solutions if s.get('method') != 'pareto_error']
                error_count = len(pareto_solutions) - len(valid_solutions)
                
                if error_count > 0:
                    self._log(f"  ⚠ {error_count} solutions failed during computation", 'warning')
                    # Log details of failed solutions
                    for sol in pareto_solutions:
                        if sol.get('method') == 'pareto_error':
                            self._log(f"    Solution {sol.get('solution_idx', '?')}: {sol.get('error', 'Unknown error')}", 'debug')
                
                if len(valid_solutions) > 0:
                    self._log(f"  ✓ {len(valid_solutions)} valid solutions", 'success')
                    
                    # Calculate statistics
                    intensities = [s['intensity_field'] for s in valid_solutions]
                    focalities = [s['focality'] for s in valid_solutions]
                    times = [s.get('time_seconds', 0) for s in valid_solutions]
                    improvements = [s.get('improvements', 0) for s in valid_solutions]
                    
                    self._log("", 'default')
                    self._log("Solution Statistics:", 'info')
                    self._log(f"  Intensity (V/m): min={min(intensities):.6f}, max={max(intensities):.6f}, avg={np.mean(intensities):.6f}", 'info')
                    self._log(f"  Focality (V/m):  min={min(focalities):.6f}, max={max(focalities):.6f}, avg={np.mean(focalities):.6f}", 'info')
                    self._log(f"  Time per solution: min={min(times):.1f}s, max={max(times):.1f}s, avg={np.mean(times):.1f}s", 'info')
                    self._log(f"  Improvements per solution: min={min(improvements)}, max={max(improvements)}, avg={np.mean(improvements):.1f}", 'info')
                    
                    pareto_solutions = valid_solutions
                    self._log("", 'default')
                    self._log(f"✓ Parallel generation complete! {len(pareto_solutions)} Pareto-optimal solutions ready", 'success')
                else:
                    self._log(f"  ✗ All solutions failed validation", 'error')
                    pareto_solutions = []
            else:
                self._log(f"Parallel generation failed or returned no results", 'error')
                # Return empty list rather than None to allow continued processing
                pareto_solutions = []
        else:
            # Serial processing (fallback)
            pareto_solutions = []
            for i in range(n_solutions):
                # Progress update every solution
                progress_pct = int(((i + 1) / n_solutions) * 100)
                self._log(f"Generating solution {i+1}/{n_solutions} ({progress_pct}% complete)...", 'info')
                
                # Use random search with dual objective evaluation
                best_cost = [float('inf'), float('inf')]
                best_electrodes = None
                best_cr = 0
                
                np.random.seed(42 + i)
                
                for _ in range(max_iter_per_solution):
                    electrodes = np.random.choice(self.num_electrodes, size=4, replace=False)
                    current_ratio = np.random.randint(0, 101)  # 0-100 for current ratio percentage
                    
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
        
        self._log(f"\n{'='*60}", 'default')
        self._log(f"PARETO FRONT GENERATION COMPLETE", 'info')
        self._log(f"{'='*60}", 'default')
        
        if pareto_solutions and len(pareto_solutions) > 0:
            intensities = [s['intensity_field'] for s in pareto_solutions]
            focalities = [s['focality'] for s in pareto_solutions]
            ratios = [s['intensity_field'] / s['focality'] if s['focality'] > 0 else 0 for s in pareto_solutions]
            
            self._log(f"Solutions generated: {len(pareto_solutions)}", 'success')
            self._log(f"Intensity range: {min(intensities):.6f} - {max(intensities):.6f} V/m", 'info')
            self._log(f"Focality range: {min(focalities):.6f} - {max(focalities):.6f} V/m", 'info')
            self._log(f"Focality ratio range: {min(ratios):.2f} - {max(ratios):.2f}", 'info')
            
            # Identify best solutions
            best_intensity_idx = intensities.index(max(intensities))
            best_focality_idx = focalities.index(min(focalities))
            best_ratio_idx = ratios.index(max(ratios))
            
            self._log("", 'default')
            self._log("Notable solutions:", 'info')
            self._log(f"  Max intensity: Solution {best_intensity_idx+1} - {intensities[best_intensity_idx]:.6f} V/m", 'info')
            self._log(f"    Electrodes: {pareto_solutions[best_intensity_idx]['electrodes']}", 'debug')
            self._log(f"  Best focality: Solution {best_focality_idx+1} - {focalities[best_focality_idx]:.6f} V/m", 'info')
            self._log(f"    Electrodes: {pareto_solutions[best_focality_idx]['electrodes']}", 'debug')
            self._log(f"  Best ratio: Solution {best_ratio_idx+1} - {ratios[best_ratio_idx]:.2f}", 'info')
            self._log(f"    Electrodes: {pareto_solutions[best_ratio_idx]['electrodes']}", 'debug')
        else:
            self._log(f"Failed to generate any valid Pareto solutions", 'error')
            self._log(f"Check logs above for error details", 'error')
        
        self._log(f"{'='*60}\n", 'default')
        
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
        
        self._log(f"Starting simple random search optimization...", 'info')
        self._log(f"Target voxels: {len(self.target_indices)}", 'info')
        self._log(f"Max iterations: {max_iter}", 'info')
        
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
                self._log(f"  Iteration {i+1}: New best cost = {best_cost:.6f}, electrodes = {best_electrodes}", 'info')
        
        solution = {
            'electrodes': best_electrodes.tolist(),
            'cost': float(best_cost),
            'field_strength': 1.0 / best_cost if best_cost > 0 else 0,
            'current_ratio': int(best_current_ratio),
            'iterations': max_iter,
            'method': 'random_search'
        }
        
        self.optimization_results.append(solution)
        
        self._log(f"\nOptimization complete!", 'success')
        self._log(f"Best electrodes: {solution['electrodes']}", 'info')
        self._log(f"Field strength: {solution['field_strength']:.6f} V/m", 'info')
        
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
