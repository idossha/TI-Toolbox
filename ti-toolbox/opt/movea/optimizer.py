"""
TI electrode optimization using scipy's differential_evolution
"""

import numpy as np
from scipy.optimize import differential_evolution
from pathlib import Path
from core.roi import find_target_voxels, validate_ti_montage
from core.calc import calculate_ti_field_from_leadfield
import concurrent.futures
import threading
from functools import partial
import time


def _evaluate_montage_parallel(args):
    """
    Worker function for parallel montage evaluation (thread-safe)
    
    Args:
        args: Tuple of (optimizer_ref, individual_idx, individual)
    
    Returns:
        tuple: (individual_idx, objectives)
    """
    try:
        optimizer_ref, individual_idx, individual = args
        electrodes = individual[:4].astype(int)
        current_ratio = individual[4] if len(individual) > 4 else 0
        
        objectives = optimizer_ref.evaluate_montage(
            electrodes, 
            current_ratio, 
            return_dual_objective=True
        )
        
        return individual_idx, objectives
    except Exception as e:
        return individual_idx, np.array([float('inf'), float('inf')])


class TIOptimizer:
    """TI electrode montage optimizer using scipy (no geatpy dependency)"""

    def __init__(self, leadfield_matrix, voxel_positions, num_electrodes=75, progress_callback=None,
                 total_current=2.0, current_step=0.1, channel_limit=1.5):
        """
        Initialize TI optimizer with scipy backend

        Args:
            leadfield_matrix: Leadfield matrix [n_electrodes, n_voxels, 3]
            voxel_positions: Voxel MNI coordinates [n_voxels, 3]
            num_electrodes: Number of electrodes in cap
            progress_callback: Optional callback function(message, type) for progress updates
            total_current: Maximum combined current across both electrode pairs in mA (default: 2.0)
            current_step: Minimum current increment in mA (default: 0.1)
            channel_limit: Maximum current per electrode in mA (default: 1.5)
        """
        self.lfm = leadfield_matrix
        self.positions = voxel_positions
        self.num_electrodes = num_electrodes
        self.target_indices = None
        self.optimization_results = []
        self._eval_count = 0
        self._progress_callback = progress_callback
        self._best_cost = float('inf')
        self._best_solution = None
        self._generation_results = []

        # Current constraints - using continuous optimization within safety limits
        self.total_current = total_current
        self.current_step = current_step  # Kept for compatibility but not used in continuous optimization
        self.channel_limit = channel_limit

    def _generate_valid_current_ratios(self):
        """
        Generate valid current ratio combinations based on safety constraints.

        Similar to ex.ti_sim.generate_current_ratios but adapted for MOVEA's
        asymmetric current distribution approach.
        """
        ratios = []
        epsilon = self.current_step * 0.01

        # For MOVEA, current_ratio affects the balance between pairs
        # current_ratio ranges from -max_ratio to +max_ratio
        # where max_ratio is based on total_current and channel_limit constraints

        # Calculate maximum allowable current ratio
        # Total current across both pairs must not exceed total_current
        # Each pair starts with total_current/2, current_ratio adjusts the balance
        base_current = self.total_current / 2.0
        max_ratio = min(
            self.channel_limit - base_current,  # Don't exceed channel limit
            base_current,                      # Don't go negative
            self.total_current - self.current_step  # Ensure some current in both pairs
        )

        if max_ratio < self.current_step - epsilon:
            max_ratio = self.current_step
            if self._progress_callback:
                self._progress_callback(
                    f"Warning: Channel limit ({self.channel_limit} mA) constrains current ratio to {max_ratio:.1f}",
                    'warning'
                )

        # Generate valid current ratios
        base_current = self.total_current / 2.0
        current_ratio = -max_ratio
        while current_ratio <= max_ratio + epsilon:
            # Check if this ratio creates valid currents for both pairs
            pair1_current = base_current + current_ratio  # First pair
            pair2_current = base_current - current_ratio  # Second pair

            # Both pairs must be within channel limits and above minimum
            # Total current must not exceed total_current limit
            total_current_used = pair1_current + pair2_current
            if (pair1_current <= self.channel_limit + epsilon and
                pair2_current <= self.channel_limit + epsilon and
                pair1_current >= self.current_step - epsilon and
                pair2_current >= self.current_step - epsilon and
                total_current_used <= self.total_current + epsilon):

                ratios.append(current_ratio)
            current_ratio += self.current_step

        self.valid_current_ratios = ratios

        if self._progress_callback:
            self._progress_callback(
                f"Generated {len(ratios)} valid current ratios (range: {ratios[0]:.2f} to {ratios[-1]:.2f})",
                'info'
            )

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

        # Validate current ratio against continuous bounds
        max_ratio = min(self.channel_limit - self.total_current/2.0, self.total_current/2.0)
        if abs(current_ratio) > max_ratio + 1e-6:
            if return_dual_objective:
                return np.array([np.inf, np.inf])
            return np.inf

        if not validate_ti_montage(electrode_indices, self.num_electrodes):
            if return_dual_objective:
                return np.array([np.inf, np.inf])
            return np.inf

        e1, e2, e3, e4 = electrode_indices

        # Ensure indices are within bounds
        if np.any(electrode_indices >= self.num_electrodes) or np.any(electrode_indices < 0):
            if return_dual_objective:
                return np.array([np.inf, np.inf])
            return np.inf

        # Create stimulation patterns (bipolar pairs)
        # Each pair uses the allocated current for that pair
        base_current = self.total_current / 2.0
        pair1_current = base_current + current_ratio
        pair2_current = base_current - current_ratio

        stim1 = np.zeros(self.num_electrodes)
        stim1[e1] = pair1_current
        stim1[e2] = -pair1_current

        stim2 = np.zeros(self.num_electrodes)
        stim2[e3] = pair2_current
        stim2[e4] = -pair2_current

        if return_dual_objective:
            # Calculate full brain field for focality
            ti_field_full = calculate_ti_field_from_leadfield(self.lfm, stim1, stim2, target_indices=None)
            ti_field_target = ti_field_full[self.target_indices]

            # Objective 1: Maximize target field (minimize reciprocal)
            avg_target = np.average(ti_field_target)
            obj1 = 1.0 / (avg_target + 1e-10)

            # Objective 2: Minimize whole brain field (focality)
            obj2 = np.mean(ti_field_full)

            return np.array([obj1, obj2])
        else:
            # Single objective: maximize target field only
            ti_field = calculate_ti_field_from_leadfield(self.lfm, stim1, stim2, self.target_indices)
            avg_field = np.average(ti_field)
            cost = 1.0 / (avg_field + 1e-10)
            return cost

    def _objective_wrapper(self, x):
        """Wrapper for scipy optimizer (single objective)"""
        self._eval_count += 1
        if self._eval_count % 100 == 0:
            self._log(f"  Evaluations: {self._eval_count}", 'info')

        # x contains [e1, e2, e3, e4, current_ratio]
        current_ratio = x[4] if len(x) > 4 else 0

        # Evaluate dual objectives for visualization purposes
        objectives = self.evaluate_montage(x[:4], current_ratio=current_ratio, return_dual_objective=True)
        cost = objectives[0]  # Single objective for optimization

        # Track best solution found so far
        if cost < self._best_cost:
            self._best_cost = cost
            self._best_solution = x.copy()

        # Store sample of evaluated solutions for visualization (every 20th evaluation to avoid too many)
        if self._eval_count % 20 == 0:
            # Use evaluation count as generation number for plotting
            generation_num = self._eval_count // 50  # Approximate generations
            if generation_num >= len(self._generation_results):
                # Calculate currents from current_ratio
                current_ratio = float(x[4]) if len(x) > 4 else 0.0
                base_current = self.total_current / 2.0
                pair1_current = base_current + current_ratio
                pair2_current = base_current - current_ratio

                result = {
                    'electrodes': np.round(x[:4]).astype(int).tolist(),
                    'cost': float(cost),
                    'field_strength': 1.0 / cost if cost > 0 else 0,
                    'current_ratio': current_ratio,
                    'pair1_current_mA': float(pair1_current),
                    'pair2_current_mA': float(pair2_current),
                    'total_current_mA': float(pair1_current + pair2_current),
                    'generation': generation_num,
                    'evaluations': self._eval_count,
                    'intensity_field': 1.0 / objectives[0] if objectives[0] > 0 else 0,
                    'focality': float(objectives[1])
                }
                self._generation_results.append(result)

        return cost

    def _manual_optimization_loop(self, bounds, max_generations, population_size):
        """
        Fallback optimization loop when differential evolution fails.
        Uses a simple but efficient genetic algorithm approach.
        """
        self._log(f"Starting fallback optimization with {population_size} population, {max_generations} generations...", 'info')

        # Initialize population more efficiently
        num_params = len(bounds)
        population = np.zeros((population_size, num_params), dtype=int)
        
        # Generate diverse initial population
        base_current = self.total_current / 2.0
        max_ratio = min(self.channel_limit - base_current, base_current)
        for i in range(population_size):
            electrodes = np.random.choice(self.num_electrodes, size=4, replace=False)
            current_ratio = np.random.uniform(-max_ratio, max_ratio)
            population[i] = np.concatenate([electrodes, [current_ratio]])

        # Use threading for parallel evaluation
        from concurrent.futures import ThreadPoolExecutor
        
        # Evaluate initial population in parallel
        with ThreadPoolExecutor(max_workers=min(4, population_size)) as executor:
            fitness_scores = np.array(list(executor.map(self._objective_wrapper, population)))
        
        best_idx = np.argmin(fitness_scores)
        best_individual = population[best_idx].copy()
        best_fitness = fitness_scores[best_idx]

        self._log(f"Initial best fitness: {best_fitness:.6f}", 'info')

        # Genetic algorithm with elitism
        elite_size = max(2, population_size // 10)
        
        for gen in range(max_generations):
            # Sort population by fitness
            sorted_indices = np.argsort(fitness_scores)
            
            # Keep elite individuals
            new_population = population[sorted_indices[:elite_size]].copy()
            
            # Generate rest of population
            while len(new_population) < population_size:
                # Tournament selection
                parent1_idx = sorted_indices[np.random.randint(0, population_size // 2)]
                parent2_idx = sorted_indices[np.random.randint(0, population_size // 2)]
                
                # Crossover for electrodes
                if np.random.random() < 0.8:
                    # Uniform crossover ensuring no duplicates
                    child = population[parent1_idx].copy()
                    electrode_pool = np.unique(np.concatenate([
                        population[parent1_idx][:4],
                        population[parent2_idx][:4]
                    ]))
                    if len(electrode_pool) >= 4:
                        child[:4] = np.random.choice(electrode_pool, 4, replace=False)
                    # Blend current ratio
                    child[4] = (population[parent1_idx][4] + population[parent2_idx][4]) // 2
                else:
                    child = population[parent1_idx].copy()
                
                # Mutation
                if np.random.random() < 0.3:
                    mut_idx = np.random.randint(0, 4)
                    available = list(range(self.num_electrodes))
                    for e in child[:4]:
                        if e in available:
                            available.remove(e)
                    if available:
                        child[mut_idx] = np.random.choice(available)
                
                new_population = np.vstack([new_population, child])
            
            population = new_population[:population_size]
            
            # Parallel evaluation
            with ThreadPoolExecutor(max_workers=min(4, population_size)) as executor:
                fitness_scores = np.array(list(executor.map(self._objective_wrapper, population)))
            
            current_best_idx = np.argmin(fitness_scores)
            current_best_fitness = fitness_scores[current_best_idx]

            # Update best solution
            if current_best_fitness < best_fitness:
                best_individual = population[current_best_idx].copy()
                best_fitness = current_best_fitness
                self._log(f"Generation {gen+1}: New best fitness: {best_fitness:.6f}", 'info')

            self._eval_count = (gen + 1) * population_size

        self._log(f"Optimization completed. Best fitness: {best_fitness:.6f}, Evaluations: {self._eval_count}", 'success')

        # Create result object similar to differential_evolution
        class ManualResult:
            def __init__(self, x, fun, success=True, nfev=None):
                self.x = x
                self.fun = fun
                self.success = success
                self.nfev = nfev

        return ManualResult(best_individual, best_fitness, success=True, nfev=self._eval_count)


    def optimize(self, max_generations=500, population_size=30,
                 preset_target=None, roi_radius_mm=10):
        """
        Run differential evolution optimization

        Args:
            max_generations: Number of generations (iterations)
            population_size: Population size
            preset_target: Preset target name or MNI coordinate
            roi_radius_mm: ROI radius in mm

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
        popsize_multiplier = max(3, population_size // 5)
        actual_population = popsize_multiplier * 5

        self._log(f"\n{'='*60}", 'default')
        self._log(f"MOVEA Optimization - Differential Evolution", 'info')
        self._log(f"{'='*60}", 'default')
        self._log(f"Target voxels: {len(self.target_indices)}", 'info')
        self._log(f"Max generations: {max_generations}", 'info')
        self._log(f"Requested population: {population_size}", 'info')
        self._log(f"Actual population: {actual_population} (popsize={popsize_multiplier} × 5 params)", 'info')
        self._log(f"Expected evaluations: ~{max_generations * actual_population}", 'info')
        self._log(f"{'='*60}\n", 'default')

        # Define bounds: 4 electrodes + 1 current ratio (continuous within safety limits)
        base_current = self.total_current / 2.0  # Should be 1.0 mA
        max_ratio = min(self.channel_limit - base_current, base_current)  # min(1.9-1.0, 1.0) = 0.9
        current_bounds = (-max_ratio, max_ratio)  # (-0.9, 0.9)


        bounds = [(0, self.num_electrodes - 1)] * 4 + [current_bounds]

        self._eval_count = 0
        self._best_cost = float('inf')
        self._best_solution = None
        self._generation_results = []

        # Try differential evolution, but handle potential issues
        try:
            self._log("Attempting differential evolution optimization...", 'info')
            result = differential_evolution(
                self._objective_wrapper,
                bounds,
                maxiter=max_generations,
                popsize=popsize_multiplier,  # This is a multiplier!
                seed=42,
                atol=0.001,
                tol=0.001,
                polish=False,  # Don't polish since we need integers
                workers=1  # Disable parallel processing to avoid map-like callable issues
            )
            self._log("Differential evolution completed successfully", 'success')
        except Exception as de_error:
            # If differential evolution fails, fall back to manual optimization loop
            error_str = str(de_error)
            self._log(f"Differential evolution failed: {error_str}", 'warning')
            if "map-like callable" in error_str:
                self._log("Detected map-like callable error. Using manual optimization loop...", 'warning')
            else:
                self._log(f"Other optimization error, using manual optimization loop...", 'warning')
            result = self._manual_optimization_loop(bounds, max_generations, population_size)

        # Extract best solution
        # Round only electrode indices, keep current_ratio as float
        best_electrodes = np.round(result.x[:4]).astype(int)
        best_current_ratio = result.x[4] if len(result.x) > 4 else 0.0
        best_cost = result.fun

        # Ensure valid solution
        best_electrodes = np.clip(best_electrodes, 0, self.num_electrodes - 1)

        # Calculate actual currents for each pair
        base_current = self.total_current / 2.0
        pair1_current = base_current + best_current_ratio
        pair2_current = base_current - best_current_ratio

        solution = {
            'electrodes': best_electrodes.tolist(),
            'cost': float(best_cost),
            'field_strength': 1.0 / best_cost if best_cost > 0 else 0,
            'current_ratio': float(best_current_ratio),
            'pair1_current_mA': float(pair1_current),
            'pair2_current_mA': float(pair2_current),
            'total_current_mA': float(pair1_current + pair2_current),
            'generations': max_generations,
            'population': population_size,
            'method': 'differential_evolution' if hasattr(result, 'success') else 'manual_genetic',
            'success': result.success if hasattr(result, 'success') else True,
            'evaluations': getattr(result, 'nfev', self._eval_count)
        }

        # Store generation results for convergence plotting
        self.optimization_results = self._generation_results.copy()

        # Also store the final solution as the last result
        if not self.optimization_results or self.optimization_results[-1]['cost'] != solution['cost']:
            # Add dual objectives to final solution for visualization
            final_objectives = self.evaluate_montage(best_electrodes, best_current_ratio, return_dual_objective=True)
            solution['intensity_field'] = 1.0 / final_objectives[0] if final_objectives[0] > 0 else 0
            solution['focality'] = float(final_objectives[1])
            solution['generation'] = max_generations
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

    def generate_pareto_solutions(self, n_solutions=20, max_generations=50, n_cores=None):
        """
        Generate Pareto-optimal solutions using NSGA-II style multi-objective optimization
        
        Args:
            n_solutions: Population size (number of solutions to maintain)
            max_generations: Number of generations to evolve
            n_cores: Number of CPU cores to use (None = auto)
        
        Returns:
            list: List of non-dominated solution dictionaries
        """
        if self.target_indices is None:
            raise ValueError("Target not set. Call set_target() first.")
        
        if n_cores is None:
            n_cores = min(4, max(1, threading.active_count() - 1))
        
        self._log(f"\n{'='*60}", 'default')
        self._log("MOVEA Multi-Objective Optimization (NSGA-II style)", 'info')
        self._log(f"{'='*60}", 'default')
        self._log(f"Population size: {n_solutions}", 'info')
        self._log(f"Generations: {max_generations}", 'info')
        self._log(f"Parallel threads: {n_cores}", 'info')
        self._log(f"{'='*60}\n", 'default')
        
        start_time = time.time()
        
        # Initialize population with random solutions
        population = []
        for i in range(n_solutions):
            # Random electrode indices and current ratio
            electrodes = np.random.choice(self.num_electrodes, size=4, replace=False)
            base_current = self.total_current / 2.0
            max_ratio = min(self.channel_limit - base_current, base_current)
            current_ratio = np.random.uniform(-max_ratio, max_ratio)
            individual = np.concatenate([electrodes, [current_ratio]])
            population.append(individual)
        
        population = np.array(population)
        
        # Evolution loop
        best_pareto_front = []
        
        for gen in range(max_generations):
            # Evaluate population in parallel
            objectives = self._evaluate_population_parallel(population, n_cores)
            
            # Find non-dominated solutions
            pareto_indices = self._find_pareto_front(objectives)
            
            # Update best Pareto front
            current_pareto = []
            for idx in pareto_indices:
                solution = self._create_solution_dict(population[idx], objectives[idx])
                current_pareto.append(solution)
            
            if len(current_pareto) > len(best_pareto_front):
                best_pareto_front = current_pareto
            
            # Progress update every generation
            self._log(f"Generation {gen + 1}/{max_generations}: {len(pareto_indices)} non-dominated solutions", 'info')
            
            # Create next generation
            if gen < max_generations - 1:
                population = self._create_next_generation(
                    population, objectives, pareto_indices, n_solutions
                )
        
        elapsed = time.time() - start_time
        
        self._log(f"\n{'='*60}", 'default')
        self._log(f"Multi-objective optimization completed in {elapsed:.1f}s", 'success')
        self._log(f"Final Pareto front: {len(best_pareto_front)} solutions", 'info')
        self._log(f"{'='*60}\n", 'default')
        
        # Create solution dicts for all final population members
        all_solutions = []
        final_objectives = self._evaluate_population_parallel(population, n_cores)
        for i, (individual, objectives) in enumerate(zip(population, final_objectives)):
            solution = self._create_solution_dict(individual, objectives)
            all_solutions.append(solution)

        # Sort Pareto front by intensity field (descending)
        best_pareto_front.sort(key=lambda x: x['intensity_field'], reverse=True)

        return best_pareto_front, all_solutions
    
    def _evaluate_population_parallel(self, population, n_cores):
        """Evaluate population objectives in parallel using threads"""
        objectives = np.zeros((len(population), 2))
        
        # Prepare arguments for parallel evaluation
        args_list = [(self, i, ind) for i, ind in enumerate(population)]
        
        # Use ThreadPoolExecutor for GUI-friendly parallelism
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_cores) as executor:
            futures = [executor.submit(_evaluate_montage_parallel, args) for args in args_list]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    idx, obj = future.result()
                    objectives[idx] = obj
                except Exception as e:
                    self._log(f"Evaluation error: {str(e)}", 'debug')
                    # Failed evaluations get infinite cost
                    idx = args_list[futures.index(future)][1]
                    objectives[idx] = [float('inf'), float('inf')]
        
        return objectives
    
    def _find_pareto_front(self, objectives):
        """Find indices of non-dominated solutions"""
        n_solutions = len(objectives)
        is_dominated = np.zeros(n_solutions, dtype=bool)
        
        for i in range(n_solutions):
            if is_dominated[i]:
                continue
            
            for j in range(n_solutions):
                if i == j or is_dominated[j]:
                    continue
                
                # Check if solution j dominates solution i
                # (better in all objectives)
                if np.all(objectives[j] <= objectives[i]) and np.any(objectives[j] < objectives[i]):
                    is_dominated[i] = True
                    break
        
        return np.where(~is_dominated)[0]
    
    def _create_next_generation(self, population, objectives, pareto_indices, target_size):
        """Create next generation using tournament selection and crossover"""
        next_gen = []
        
        # Always include Pareto front solutions (elitism)
        for idx in pareto_indices:
            next_gen.append(population[idx].copy())
        
        # Fill rest with offspring
        while len(next_gen) < target_size:
            # Tournament selection
            parent1 = self._tournament_selection(population, objectives)
            parent2 = self._tournament_selection(population, objectives)
            
            # Crossover
            if np.random.random() < 0.8:  # 80% crossover rate
                offspring = self._crossover(parent1, parent2)
            else:
                offspring = parent1.copy()
            
            # Mutation
            offspring = self._mutate(offspring)
            
            next_gen.append(offspring)
        
        return np.array(next_gen[:target_size])
    
    def _tournament_selection(self, population, objectives, tournament_size=3):
        """Tournament selection based on dominance ranking"""
        indices = np.random.choice(len(population), tournament_size, replace=False)
        
        # Find best individual in tournament
        best_idx = indices[0]
        for idx in indices[1:]:
            # Check if idx dominates best_idx
            if np.all(objectives[idx] <= objectives[best_idx]) and np.any(objectives[idx] < objectives[best_idx]):
                best_idx = idx
        
        return population[best_idx].copy()
    
    def _crossover(self, parent1, parent2):
        """Uniform crossover for electrode indices and blend for current ratio"""
        offspring = parent1.copy()
        
        # Crossover electrode indices (ensure no duplicates)
        electrode_pool = np.unique(np.concatenate([parent1[:4], parent2[:4]]))
        if len(electrode_pool) >= 4:
            offspring[:4] = np.random.choice(electrode_pool, 4, replace=False)
        
        # Blend current ratios
        if len(parent1) > 4 and len(parent2) > 4:
            # Arithmetic crossover for continuous values
            offspring[4] = (parent1[4] + parent2[4]) / 2.0
        
        return offspring
    
    def _mutate(self, individual, mutation_rate=0.2):
        """Mutate individual with given probability"""
        mutated = individual.copy()
        
        # Mutate electrode indices
        if np.random.random() < mutation_rate:
            # Replace one electrode with a random one
            idx_to_mutate = np.random.randint(0, 4)
            available = list(range(self.num_electrodes))
            for e in mutated[:4]:
                if int(e) in available:
                    available.remove(int(e))
            if available:
                mutated[idx_to_mutate] = np.random.choice(available)
        
        # Mutate current ratio
        if len(mutated) > 4 and np.random.random() < mutation_rate:
            # Mutate within continuous bounds
            base_current = self.total_current / 2.0
            max_ratio = min(self.channel_limit - base_current, base_current)
            mutated[4] = np.random.uniform(-max_ratio, max_ratio)
        
        return mutated
    
    def _create_solution_dict(self, individual, objectives):
        """Create solution dictionary from individual and objectives"""
        electrodes = individual[:4].astype(int)
        current_ratio = float(individual[4]) if len(individual) > 4 else 0.0

        # Calculate actual currents from current_ratio
        base_current = self.total_current / 2.0
        pair1_current = base_current + current_ratio
        pair2_current = base_current - current_ratio

        return {
            'electrodes': electrodes.tolist(),
            'current_ratio': current_ratio,
            'pair1_current_mA': float(pair1_current),
            'pair2_current_mA': float(pair2_current),
            'total_current_mA': float(pair1_current + pair2_current),
            'intensity_cost': float(objectives[0]),
            'intensity_field': 1.0 / objectives[0] if objectives[0] > 0 else 0,
            'focality': float(objectives[1]),
            'method': 'pareto_nsga2',
            'focality_ratio': (1.0 / objectives[0]) / objectives[1] if objectives[1] > 0 else 0
        }

    def _get_preset_target(self, target_name):
        """Get MNI coordinates for preset targets from external config file"""
        import json
        import os

        # Load presets from roi_presets.json
        presets_file = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   'roi_presets.json')

        presets = {}
        if os.path.exists(presets_file):
            try:
                with open(presets_file, 'r') as f:
                    data = json.load(f)
                    presets = data.get('regions', {})
            except Exception as e:
                self._log(f"Warning: Could not load presets file: {e}", 'warning')

        if isinstance(target_name, str):
            target_name = target_name.lower()
            if target_name in presets:
                return np.array(presets[target_name]['mni'])
            else:
                # Try to parse as coordinates
                try:
                    coords = [float(x) for x in target_name.split(',')]
                    if len(coords) == 3:
                        return np.array(coords)
                except:
                    pass
                available_presets = list(presets.keys()) if presets else []
                raise ValueError(
                    f"Unknown target: {target_name}. "
                    f"Available presets: {available_presets} or 'x,y,z' coordinates"
                )
        else:
            return np.array(target_name)




