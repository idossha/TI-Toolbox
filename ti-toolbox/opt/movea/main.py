"""
MOVEA Main Optimization Workflow
Handles the complete MOVEA optimization process from setup to results
"""

import os
import traceback
from pathlib import Path

from .optimizer import TIOptimizer
from .visualizer import MOVEAVisualizer
from .montage_formatter import MontageFormatter


def run_optimization(config, progress_callback=None):
    """
    Run complete MOVEA optimization workflow

    Args:
        config: Dictionary with all optimization parameters
        progress_callback: Optional callback function(message, type) for progress updates

    Returns:
        dict: Results containing optimized montage, output files, etc.
    """
    def _log(message, msg_type='info'):
        """Send log message through callback or fallback to print"""
        if progress_callback:
            progress_callback(message, msg_type)
        else:
            print(message)

    try:
        # Extract configuration
        lfm = config['lfm']
        positions = config['positions']
        num_electrodes = config['num_electrodes']
        target = config['target']
        roi_radius = config['roi_radius_mm']
        output_dir = config['output_dir']
        target_name = config.get('target_name', 'ROI')

        # Optimization parameters
        generations = config['generations']
        population = config['population']
        generate_pareto = config.get('generate_pareto', False)
        n_pareto_solutions = config.get('pareto_n_solutions', 20)
        pareto_max_iter = config.get('pareto_max_iter', 500)
        n_pareto_cores = config.get('pareto_n_cores', None)

        # Electrode coordinates file (optional)
        electrode_csv = config.get('electrode_coords_file')

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Create optimizer
        _log("Creating MOVEA optimizer...", 'info')
        optimizer = TIOptimizer(
            lfm, positions, num_electrodes,
            progress_callback=progress_callback,
            total_current=2.0,      # Total across both channels
            current_step=0.05,      # High resolution
            channel_limit=1.9       # Allow up to 1.9 mA per channel
        )

        # Set target
        if isinstance(target, list):
            target_str = f"[{', '.join(map(str, target))}]"
        else:
            target_str = target

        _log(f"Target: {target_str} (ROI radius: {roi_radius}mm)", 'info')

        try:
            optimizer.set_target(target, roi_radius)
        except Exception as e:
            raise ValueError(f"Failed to set target: {str(e)}")

        # Run optimization
        opt_method = config.get('opt_method', 'differential_evolution')
        _log(f"Starting optimization (Method: {opt_method}, Generations: {generations}, Population: {population})...", 'info')
        _log("This may take several minutes. Please wait...", 'info')

        result = optimizer.optimize(
            max_generations=generations,
            population_size=population
        )

        opt_time = 0  # Would need timing if we wanted to track this
        _log(f"Optimization completed ({opt_time:.1f}s)", 'success')

        # Format results
        _log("Formatting results...", 'info')

        # Create formatter
        formatter = MontageFormatter(electrode_csv, progress_callback=progress_callback)

        # Check if names were loaded
        if formatter.electrode_names:
            _log(f"✓ Loaded {len(formatter.electrode_names)} electrode names", 'success')
        else:
            _log("⚠ Using generic electrode names (E0, E1, ...)", 'warning')

        montage = formatter.format_ti_montage(result)

        # Generate Pareto front if enabled
        pareto_solutions = []
        combined_pareto_solutions = []
        combined_all_solutions = []

        # Get optimization results (always available)
        if hasattr(optimizer, 'optimization_results') and len(optimizer.optimization_results) > 0:
            sample_result = optimizer.optimization_results[0]
            if 'intensity_field' in sample_result and 'focality' in sample_result:
                # Use optimization results as background solutions
                for res in optimizer.optimization_results:
                    if 'intensity_field' in res and 'focality' in res:
                        combined_all_solutions.append({
                            'electrodes': res['electrodes'],
                            'intensity_field': res['intensity_field'],
                            'focality': res['focality']
                        })

                # Find best solution from optimization
                if combined_all_solutions:
                    best_solution = max(combined_all_solutions, key=lambda x: x['intensity_field'])
                    combined_pareto_solutions.append(best_solution)

        # Generate Pareto front if enabled
        if generate_pareto:
            try:
                # Calculate generations for NSGA-II algorithm
                approx_generations = max(10, pareto_max_iter // n_pareto_solutions)
                total_evals = n_pareto_solutions * approx_generations

                # Estimate time (NSGA-II is more efficient than random search)
                est_time = max(1, total_evals // 500)
                _log(f"  Generating Pareto front using NSGA-II algorithm", 'info')
                _log(f"  Population size: {n_pareto_solutions}, Generations: {approx_generations}", 'info')
                if n_pareto_cores and n_pareto_cores > 1:
                    _log(f"  Parallel threads: {n_pareto_cores}", 'info')
                _log(f"  Estimated evaluations: {total_evals:,} (est. {est_time} min)...", 'info')

                pareto_solutions, pareto_all_solutions = optimizer.generate_pareto_solutions(
                    n_solutions=n_pareto_solutions,
                    max_generations=approx_generations,
                    n_cores=n_pareto_cores
                )

                if pareto_solutions and len(pareto_solutions) > 0:
                    # Use Pareto solutions as the main front, add Pareto all-solutions to background
                    combined_pareto_solutions = pareto_solutions
                    combined_all_solutions.extend(pareto_all_solutions)

            except Exception as pareto_err:
                _log(f"  ⚠ Pareto front generation failed, using optimization results only: {str(pareto_err)}", 'warning')
        else:
            _log("  ⓘ Pareto front generation disabled (showing optimization results only)", 'info')

        # Always export solutions CSV
        try:
            pareto_csv = os.path.join(output_dir, 'pareto_solutions.csv')
            solutions_to_export = []

            # Use Pareto solutions if available, otherwise use optimization results
            if pareto_solutions and len(pareto_solutions) > 0:
                solutions_to_export = pareto_solutions
                csv_type = "Pareto solutions"
            elif combined_all_solutions:
                # Sort by intensity field and take top solutions (like a pseudo-Pareto front)
                solutions_to_export = sorted(combined_all_solutions, key=lambda x: x['intensity_field'], reverse=True)[:min(10, len(combined_all_solutions))]
                csv_type = "Top optimization solutions"
            else:
                csv_type = "No solutions available"

            if solutions_to_export:
                with open(pareto_csv, 'w') as f:
                    f.write("Solution,Electrode1,Electrode2,Electrode3,Electrode4,Pair1_Current_mA,Pair2_Current_mA,Total_Current_mA,ROI_Field_Vm,WholeBrain_Field_Vm,Focality_Ratio\n")
                    for i, sol in enumerate(solutions_to_export):
                        # Get electrode names if available
                        e_indices = sol['electrodes']
                        if formatter.electrode_names and len(formatter.electrode_names) > max(e_indices):
                            e_names = [formatter.electrode_names[idx] for idx in e_indices]
                        else:
                            e_names = [f"E{idx}" for idx in e_indices]

                        # Get current values (use defaults if not available)
                        pair1_current = sol.get('pair1_current_mA', 1.0)
                        pair2_current = sol.get('pair2_current_mA', 1.0)
                        total_current = sol.get('total_current_mA', pair1_current + pair2_current)

                        # Calculate focality ratio (ROI field / Whole brain field)
                        focality_ratio = sol['intensity_field'] / sol['focality'] if sol['focality'] > 0 else 0

                        f.write(f"{i+1},{e_names[0]},{e_names[1]},{e_names[2]},{e_names[3]},{pair1_current:.3f},{pair2_current:.3f},{total_current:.3f},{sol['intensity_field']:.6f},{sol['focality']:.6f},{focality_ratio:.4f}\n")
                _log(f"  ✓ Solutions CSV ({csv_type}): {os.path.basename(pareto_csv)}", 'success')
            else:
                _log("  ⚠ No solutions available for CSV export", 'warning')

        except Exception as csv_err:
            _log(f"  ⚠ Solutions CSV export failed: {str(csv_err)}", 'warning')

        # Create visualizations
        _log("Creating visualizations...", 'info')
        visualizer = MOVEAVisualizer(output_dir, progress_callback=progress_callback)

        # Create single comprehensive plot
        generated_files = {}
        if combined_pareto_solutions and combined_all_solutions:
            try:
                solutions_path = os.path.join(output_dir, 'solutions_plot.png')
                visualizer.plot_pareto_front(combined_pareto_solutions, all_solutions=combined_all_solutions,
                                           save_path=solutions_path, target_name=target_name)
                _log(f"  ✓ Solutions plot: {os.path.basename(solutions_path)}", 'success')
                generated_files['solutions_plot'] = solutions_path
            except Exception as sol_plot_err:
                _log(f"  ⚠ Solutions plot failed: {str(sol_plot_err)}", 'warning')

        # Generate convergence plot for optimization results
        if hasattr(optimizer, 'optimization_results') and len(optimizer.optimization_results) > 0:
            try:
                conv_path = os.path.join(output_dir, 'convergence.png')
                visualizer.plot_convergence(optimizer.optimization_results, save_path=conv_path)
                _log(f"  ✓ Convergence plot: {os.path.basename(conv_path)}", 'success')
                generated_files['convergence'] = conv_path
            except Exception as conv_err:
                _log(f"  ⚠ Convergence plot failed: {str(conv_err)}", 'warning')

        # Save main montage CSV
        output_csv = os.path.join(output_dir, 'movea_montage.csv')
        formatter.save_montage_csv(montage, output_csv)
        generated_files['montage_csv'] = output_csv

        # Return results
        results = {
            'montage': montage,
            'optimizer': optimizer,
            'pareto_solutions': pareto_solutions,
            'generated_files': generated_files,
            'success': True
        }

        _log("="*60, 'default')
        _log("MOVEA OPTIMIZATION COMPLETE", 'success')
        _log("="*60, 'default')

        pair1 = montage['pair1']
        pair2 = montage['pair2']
        opt_info = montage['optimization']

        _log(f"Pair 1: {pair1['anode']['name']} (+{pair1['current_mA']}mA) ↔ {pair1['cathode']['name']} (-{pair1['current_mA']}mA)", 'default')
        _log(f"Pair 2: {pair2['anode']['name']} (+{pair2['current_mA']}mA) ↔ {pair2['cathode']['name']} (-{pair2['current_mA']}mA)", 'default')
        _log(f"Field Strength: {opt_info['field_strength_V/m']:.6f} V/m", 'default')
        _log(f"Optimization Cost: {opt_info['cost']:.6f}", 'default')
        _log("="*60, 'default')
        _log(f"Results saved to: {output_dir}", 'success')

        for name, path in generated_files.items():
            _log(f"  • {os.path.basename(path)}", 'default')

        _log("="*60, 'default')

        return results

    except Exception as e:
        error_msg = f"Error during optimization: {str(e)}"
        if progress_callback:
            progress_callback(error_msg, 'error')
            progress_callback(traceback.format_exc(), 'debug')
        else:
            print(error_msg)
            print(traceback.format_exc())

        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }