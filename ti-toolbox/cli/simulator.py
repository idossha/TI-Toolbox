#!/usr/bin/env python3
"""
TI-Toolbox Simulator CLI

A Click-based command-line interface for running TI/mTI simulations.
Provides both interactive and direct execution modes.

Usage:
    # Interactive mode
    python simulator_cli.py

    # Direct mode (for GUI/scripting)
    python simulator_cli.py run --subject 101 --montage MyMontage --intensity 2.0

    # List available subjects
    python simulator_cli.py list-subjects

    # List montages for a subject
    python simulator_cli.py list-montages --subject 101 --eeg-net EGI_template.csv
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import click

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import get_path_manager, list_subjects, reset_path_manager
from sim import (
    ConductivityType,
    ElectrodeConfig,
    IntensityConfig,
    MontageConfig,
    ParallelConfig,
    SimulationConfig,
    load_montages,
    run_simulation,
)
from sim.montage_loader import load_flex_montages, load_montage_file, parse_flex_montage


# =============================================================================
# STYLING HELPERS
# =============================================================================

COLORS = {
    'header': 'cyan',
    'success': 'green',
    'warning': 'yellow',
    'error': 'red',
    'info': 'blue',
    'prompt': 'white',
}


def echo_header(text: str):
    """Print a styled header."""
    click.secho(f"\n{'=' * 50}", fg=COLORS['header'], bold=True)
    click.secho(f"  {text}", fg=COLORS['header'], bold=True)
    click.secho(f"{'=' * 50}\n", fg=COLORS['header'], bold=True)


def echo_section(text: str):
    """Print a styled section header."""
    click.secho(f"\n{text}", fg=COLORS['header'], bold=True)
    click.secho("-" * len(text), fg=COLORS['header'])


def echo_success(text: str):
    """Print a success message."""
    click.secho(f"✓ {text}", fg=COLORS['success'])


def echo_warning(text: str):
    """Print a warning message."""
    click.secho(f"⚠ {text}", fg=COLORS['warning'])


def echo_error(text: str):
    """Print an error message."""
    click.secho(f"✗ {text}", fg=COLORS['error'])


def echo_info(text: str):
    """Print an info message."""
    click.secho(f"ℹ {text}", fg=COLORS['info'])


# =============================================================================
# INTERACTIVE PROMPTS
# =============================================================================

def display_subjects_table(subjects: List[str]) -> None:
    """Display subjects in a multi-column table."""
    if not subjects:
        echo_warning("No subjects found")
        return
    
    max_rows = 10
    num_cols = (len(subjects) + max_rows - 1) // max_rows
    
    for row in range(max_rows):
        line = ""
        for col in range(num_cols):
            idx = col * max_rows + row
            if idx < len(subjects):
                line += f"{idx + 1:3d}. {subjects[idx]:<25}"
        if line:
            click.echo(line)


def prompt_subjects(subjects: List[str]) -> List[str]:
    """Prompt user to select subjects."""
    echo_section("Available Subjects")
    display_subjects_table(subjects)
    
    click.echo()
    selection = click.prompt(
        click.style("Enter subject numbers (comma-separated, e.g., 1,2,3)", fg='white'),
        type=str
    )
    
    selected = []
    for num_str in selection.split(','):
        try:
            num = int(num_str.strip())
            if 1 <= num <= len(subjects):
                selected.append(subjects[num - 1])
            else:
                echo_warning(f"Invalid number: {num}")
        except ValueError:
            # Check if it's a subject ID directly
            if num_str.strip() in subjects:
                selected.append(num_str.strip())
            else:
                echo_warning(f"Invalid input: {num_str}")
    
    if not selected:
        echo_error("No valid subjects selected")
        raise click.Abort()
    
    return selected


def prompt_conductivity() -> ConductivityType:
    """Prompt user to select conductivity type."""
    echo_section("Conductivity Type")
    click.echo("1. Isotropic (scalar)")
    click.echo("2. Anisotropic (vn)")
    click.echo("3. Anisotropic (dir)")
    click.echo("4. Anisotropic (mc)")
    
    choice = click.prompt(
        click.style("Select conductivity type", fg='white'),
        type=click.IntRange(1, 4),
        default=1
    )
    
    mapping = {
        1: ConductivityType.SCALAR,
        2: ConductivityType.VN,
        3: ConductivityType.DIR,
        4: ConductivityType.MC,
    }
    return mapping[choice]


def prompt_simulation_framework() -> str:
    """Prompt user to select simulation framework."""
    echo_section("Simulation Framework")
    click.echo("1. Montage Simulation (traditional electrode placement)")
    click.echo("2. Flex-Search Simulation (from optimization results)")
    
    choice = click.prompt(
        click.style("Select framework", fg='white'),
        type=click.IntRange(1, 2),
        default=1
    )
    
    return "montage" if choice == 1 else "flex"


def prompt_simulation_mode() -> str:
    """Prompt user to select simulation mode (TI or mTI)."""
    echo_section("Simulation Mode")
    click.echo("U. Unipolar TI (2-pair)")
    click.echo("M. Multipolar mTI (4-pair)")
    
    choice = click.prompt(
        click.style("Select mode (U/M)", fg='white'),
        type=click.Choice(['U', 'M', 'u', 'm'], case_sensitive=False),
        default='U'
    ).upper()
    
    return choice


def prompt_eeg_net(subject_id: str) -> str:
    """Prompt user to select EEG net for a subject."""
    pm = get_path_manager()
    caps = pm.list_eeg_caps(subject_id)
    
    if not caps:
        echo_warning(f"No EEG caps found for subject {subject_id}, using default")
        return "EGI_template.csv"
    
    echo_section(f"EEG Net Selection for Subject {subject_id}")
    for i, cap in enumerate(caps, 1):
        click.echo(f"{i:3d}. {cap}")
    
    choice = click.prompt(
        click.style("Select EEG net", fg='white'),
        type=click.IntRange(1, len(caps)),
        default=1
    )
    
    return caps[choice - 1]


def prompt_montages(project_dir: str, eeg_net: str, sim_mode: str) -> List[str]:
    """Prompt user to select montages."""
    try:
        montage_data = load_montage_file(project_dir, eeg_net)
    except (ValueError, FileNotFoundError):
        echo_warning("No montages found. Please create montages first.")
        return []
    
    montage_type = "uni_polar_montages" if sim_mode == "U" else "multi_polar_montages"
    available = montage_data.get(montage_type, {})
    
    if not available:
        echo_warning(f"No {montage_type} found for {eeg_net}")
        return []
    
    montage_names = list(available.keys())
    
    echo_section(f"Available Montages ({montage_type})")
    for i, name in enumerate(montage_names, 1):
        pairs = available[name]
        pairs_str = "; ".join([f"{p[0]},{p[1]}" for p in pairs])
        click.echo(f"{i:3d}. {name:<25} Pairs: {pairs_str}")
    
    click.echo()
    selection = click.prompt(
        click.style("Enter montage numbers (comma-separated)", fg='white'),
        type=str
    )
    
    selected = []
    for num_str in selection.split(','):
        try:
            num = int(num_str.strip())
            if 1 <= num <= len(montage_names):
                selected.append(montage_names[num - 1])
            else:
                echo_warning(f"Invalid number: {num}")
        except ValueError:
            echo_warning(f"Invalid input: {num_str}")
    
    return selected


def prompt_flex_outputs(selected_subjects: List[str]) -> Tuple[List[dict], str]:
    """
    Prompt user to select flex-search outputs.
    
    Returns:
        Tuple of (flex montage data list, electrode type text)
    """
    pm = get_path_manager()
    
    flex_outputs = []
    flex_paths = []
    
    for subject_id in selected_subjects:
        subject_dir = pm.get_subject_dir(subject_id)
        if not subject_dir:
            continue
        
        flex_search_dir = os.path.join(subject_dir, "flex-search")
        if not os.path.isdir(flex_search_dir):
            continue
        
        for search_name in os.listdir(flex_search_dir):
            search_dir = os.path.join(flex_search_dir, search_name)
            if not os.path.isdir(search_dir):
                continue
            
            mapping_file = os.path.join(search_dir, "electrode_mapping.json")
            if os.path.exists(mapping_file):
                try:
                    with open(mapping_file, 'r') as f:
                        data = json.load(f)
                    eeg_net = data.get('eeg_net', 'Unknown')
                    n_electrodes = len(data.get('optimized_positions', []))
                    flex_outputs.append({
                        'subject_id': subject_id,
                        'search_name': search_name,
                        'display': f"{subject_id} | {search_name}",
                        'details': f"{n_electrodes} electrodes | {eeg_net}",
                    })
                    flex_paths.append(mapping_file)
                except Exception:
                    pass
    
    if not flex_outputs:
        echo_error("No flex-search outputs found for selected subjects")
        raise click.Abort()
    
    echo_section("Available Flex-Search Outputs")
    for i, output in enumerate(flex_outputs, 1):
        click.echo(f"{i:3d}. {output['display']:<40} | {output['details']}")
    
    click.echo()
    selection = click.prompt(
        click.style("Enter output numbers (comma-separated)", fg='white'),
        type=str
    )
    
    selected_indices = []
    for num_str in selection.split(','):
        try:
            num = int(num_str.strip())
            if 1 <= num <= len(flex_outputs):
                selected_indices.append(num - 1)
        except ValueError:
            pass
    
    # Choose electrode type
    echo_section("Electrode Type")
    click.echo("1. Mapped electrodes only (use EEG net positions)")
    click.echo("2. Optimized electrodes only (use XYZ coordinates)")
    click.echo("3. Both mapped and optimized")
    
    electrode_choice = click.prompt(
        click.style("Select electrode type", fg='white'),
        type=click.IntRange(1, 3),
        default=1
    )
    
    use_mapped = electrode_choice in [1, 3]
    use_optimized = electrode_choice in [2, 3]
    electrode_type_text = ["Mapped", "Optimized", "Both"][electrode_choice - 1]
    
    # Build flex montage configs
    flex_montages = []
    for idx in selected_indices:
        mapping_file = flex_paths[idx]
        output_info = flex_outputs[idx]
        
        try:
            with open(mapping_file, 'r') as f:
                mapping_data = json.load(f)
            
            search_name = output_info['search_name']
            
            if use_mapped:
                mapped_labels = mapping_data.get('mapped_labels', [])
                if len(mapped_labels) >= 4:
                    flex_montages.append({
                        'name': f"flex_{search_name}_mapped",
                        'type': 'flex_mapped',
                        'eeg_net': mapping_data.get('eeg_net'),
                        'electrode_labels': mapped_labels[:4],
                        'pairs': [
                            [mapped_labels[0], mapped_labels[1]],
                            [mapped_labels[2], mapped_labels[3]]
                        ]
                    })
            
            if use_optimized:
                optimized_positions = mapping_data.get('optimized_positions', [])
                if len(optimized_positions) >= 4:
                    flex_montages.append({
                        'name': f"flex_{search_name}_optimized",
                        'type': 'flex_optimized',
                        'electrode_positions': optimized_positions[:4],
                        'pairs': [
                            [optimized_positions[0], optimized_positions[1]],
                            [optimized_positions[2], optimized_positions[3]]
                        ]
                    })
        except Exception as e:
            echo_warning(f"Failed to parse {mapping_file}: {e}")
    
    return flex_montages, electrode_type_text


def prompt_electrode_shape() -> str:
    """Prompt user for electrode shape."""
    return click.prompt(
        click.style("Electrode shape (rect/ellipse)", fg='white'),
        type=click.Choice(['rect', 'ellipse']),
        default='ellipse'
    )


def prompt_electrode_dimensions() -> List[float]:
    """Prompt user for electrode dimensions."""
    dims_str = click.prompt(
        click.style("Electrode dimensions in mm (x,y)", fg='white'),
        type=str,
        default='8,8'
    )
    try:
        dims = [float(x.strip()) for x in dims_str.split(',')]
        if len(dims) != 2:
            raise ValueError("Need exactly 2 dimensions")
        return dims
    except ValueError:
        echo_warning("Invalid dimensions, using default 8x8")
        return [8.0, 8.0]


def prompt_electrode_thickness() -> float:
    """Prompt user for electrode thickness."""
    return click.prompt(
        click.style("Electrode thickness in mm", fg='white'),
        type=float,
        default=4.0
    )


def prompt_intensity() -> float:
    """Prompt user for stimulation intensity."""
    return click.prompt(
        click.style("Stimulation intensity in mA", fg='white'),
        type=float,
        default=2.0
    )


def show_confirmation(
    subjects: List[str],
    conductivity: ConductivityType,
    framework: str,
    sim_mode: str,
    montages: List[str],
    electrode: ElectrodeConfig,
    intensity: float,
    eeg_nets: dict,
) -> bool:
    """Show configuration summary and get confirmation."""
    echo_header("Configuration Summary")
    
    echo_section("Subjects")
    for subj in subjects:
        eeg_net = eeg_nets.get(subj, "N/A")
        click.echo(f"  • {subj} (EEG Net: {eeg_net})")
    
    echo_section("Simulation Parameters")
    click.echo(f"  Conductivity:  {conductivity.value}")
    click.echo(f"  Framework:     {'Flex-Search' if framework == 'flex' else 'Montage'}")
    click.echo(f"  Mode:          {'Unipolar TI' if sim_mode == 'U' else 'Multipolar mTI'}")
    
    echo_section("Montages")
    for m in montages:
        click.echo(f"  • {m}")
    
    echo_section("Electrode Configuration")
    click.echo(f"  Shape:      {electrode.shape}")
    click.echo(f"  Dimensions: {electrode.dimensions[0]} x {electrode.dimensions[1]} mm")
    click.echo(f"  Thickness:  {electrode.thickness} mm")
    click.echo(f"  Intensity:  {intensity} mA")
    
    click.echo()
    return click.confirm(
        click.style("Proceed with simulation?", fg='yellow', bold=True),
        default=True
    )


# =============================================================================
# CLI COMMANDS
# =============================================================================

@click.group(invoke_without_command=True)
@click.option('--project-dir', '-p', envvar='PROJECT_DIR',
              help='Project directory path (BIDS root)')
@click.pass_context
def cli(ctx, project_dir):
    """
    TI-Toolbox Simulator CLI
    
    Run TI/mTI simulations interactively or via command-line options.
    """
    ctx.ensure_object(dict)
    
    # Initialize path manager
    pm = get_path_manager()
    if project_dir:
        try:
            pm.project_dir = project_dir
        except ValueError as e:
            echo_error(str(e))
            raise click.Abort()
    
    ctx.obj['pm'] = pm
    ctx.obj['project_dir'] = pm.project_dir
    
    # If no subcommand, run interactive mode
    if ctx.invoked_subcommand is None:
        ctx.invoke(interactive)


@cli.command()
@click.pass_context
def interactive(ctx):
    """Run the simulator in interactive mode."""
    pm = ctx.obj['pm']
    project_dir = ctx.obj['project_dir']
    
    if not project_dir:
        echo_error("Project directory not set. Use --project-dir or set PROJECT_DIR environment variable.")
        raise click.Abort()
    
    # Welcome
    echo_header("TI-Toolbox Simulator")
    click.echo(f"Project: {project_dir}")
    
    # Get available subjects
    subjects = list_subjects()
    if not subjects:
        echo_error("No subjects found in project directory")
        raise click.Abort()
    
    # Interactive prompts
    selected_subjects = prompt_subjects(subjects)
    conductivity = prompt_conductivity()
    framework = prompt_simulation_framework()
    sim_mode = "U"  # Default for flex
    
    if framework == "flex":
        sim_mode = "U"  # TI for flex-search
        echo_info("Flex-Search mode uses TI (Unipolar) simulation")
    else:
        sim_mode = prompt_simulation_mode()
    
    # EEG net selection per subject (for montage mode)
    eeg_nets = {}
    if framework != "flex":
        for subject_id in selected_subjects:
            eeg_nets[subject_id] = prompt_eeg_net(subject_id)
    
    # Montage/flex selection
    montage_names = []
    flex_montage_data = []
    
    if framework == "flex":
        flex_montage_data, electrode_type = prompt_flex_outputs(selected_subjects)
        montage_names = [m['name'] for m in flex_montage_data]
    else:
        # Use first subject's EEG net for montage selection
        first_eeg_net = eeg_nets[selected_subjects[0]]
        montage_names = prompt_montages(project_dir, first_eeg_net, sim_mode)
    
    if not montage_names:
        echo_error("No montages selected")
        raise click.Abort()
    
    # Electrode configuration
    echo_section("Electrode Configuration")
    electrode_shape = prompt_electrode_shape()
    electrode_dims = prompt_electrode_dimensions()
    electrode_thickness = prompt_electrode_thickness()
    intensity = prompt_intensity()
    
    electrode = ElectrodeConfig(
        shape=electrode_shape,
        dimensions=electrode_dims,
        thickness=electrode_thickness,
    )
    
    # Confirmation
    if not show_confirmation(
        subjects=selected_subjects,
        conductivity=conductivity,
        framework=framework,
        sim_mode=sim_mode,
        montages=montage_names,
        electrode=electrode,
        intensity=intensity,
        eeg_nets=eeg_nets,
    ):
        echo_warning("Simulation cancelled")
        raise click.Abort()
    
    # Run simulations
    echo_header("Running Simulations")
    
    all_results = []
    start_time = time.time()
    
    for subject_id in selected_subjects:
        click.echo()
        echo_info(f"Processing subject: {subject_id}")
        
        eeg_net = eeg_nets.get(subject_id, "EGI_template.csv")
        
        # Build intensity config
        intensity_config = IntensityConfig(
            pair1_ch1=intensity,
            pair1_ch2=intensity,
            pair2_ch1=intensity,
            pair2_ch2=intensity,
        )
        
        # Build simulation config
        config = SimulationConfig(
            subject_id=subject_id,
            project_dir=project_dir,
            conductivity_type=conductivity,
            intensities=intensity_config,
            electrode=electrode,
            eeg_net=eeg_net,
        )
        
        # Build montage configs
        if framework == "flex":
            montages = [parse_flex_montage(m) for m in flex_montage_data]
        else:
            montages = load_montages(
                montage_names=montage_names,
                project_dir=project_dir,
                eeg_net=eeg_net,
                include_flex=False,
            )
        
        # Progress callback
        def progress_callback(current, total, name):
            click.echo(f"  [{current}/{total}] {name}")
        
        # Run simulation
        try:
            results = run_simulation(config, montages, progress_callback=progress_callback)
            all_results.extend(results)
            
            completed = sum(1 for r in results if r.get('status') == 'completed')
            failed = sum(1 for r in results if r.get('status') == 'failed')
            
            if failed == 0:
                echo_success(f"Subject {subject_id}: {completed} simulation(s) completed")
            else:
                echo_warning(f"Subject {subject_id}: {completed} completed, {failed} failed")
                
        except Exception as e:
            echo_error(f"Subject {subject_id} failed: {e}")
    
    # Summary
    elapsed = time.time() - start_time
    total_completed = sum(1 for r in all_results if r.get('status') == 'completed')
    total_failed = sum(1 for r in all_results if r.get('status') == 'failed')
    
    echo_header("Simulation Complete")
    click.echo(f"Total simulations: {len(all_results)}")
    click.echo(f"Completed: {total_completed}")
    click.echo(f"Failed: {total_failed}")
    click.echo(f"Time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    
    if total_failed > 0:
        echo_section("Failed Simulations")
        for r in all_results:
            if r.get('status') == 'failed':
                click.echo(f"  • {r['montage_name']}: {r.get('error', 'Unknown error')}")


@cli.command()
@click.option('--subject', '-s', required=True, multiple=True,
              help='Subject ID(s) to simulate')
@click.option('--montage', '-m', multiple=True,
              help='Montage name(s) to simulate')
@click.option('--eeg-net', '-e', default='EGI_template.csv',
              help='EEG net file name')
@click.option('--conductivity', '-c',
              type=click.Choice(['scalar', 'vn', 'dir', 'mc']),
              default='scalar', help='Conductivity type')
@click.option('--intensity', '-i', type=float, default=2.0,
              help='Stimulation intensity in mA')
@click.option('--shape', type=click.Choice(['rect', 'ellipse']),
              default='ellipse', help='Electrode shape')
@click.option('--dimensions', '-d', default='8,8',
              help='Electrode dimensions (x,y in mm)')
@click.option('--thickness', '-t', type=float, default=4.0,
              help='Electrode thickness in mm')
@click.option('--parallel/--no-parallel', default=False,
              help='Enable parallel execution')
@click.option('--workers', '-w', type=int, default=0,
              help='Number of parallel workers (0=auto)')
@click.option('--flex-file', type=click.Path(exists=True),
              help='Path to flex montages JSON file')
@click.option('--dry-run', is_flag=True,
              help='Validate configuration without running simulation')
@click.pass_context
def run(ctx, subject, montage, eeg_net, conductivity, intensity,
        shape, dimensions, thickness, parallel, workers, flex_file, dry_run):
    """
    Run simulation directly with command-line options.
    
    This is the non-interactive mode for scripting and GUI integration.
    """
    pm = ctx.obj['pm']
    project_dir = ctx.obj['project_dir']
    
    if not project_dir:
        echo_error("Project directory not set")
        raise click.Abort()
    
    # Parse dimensions
    try:
        dims = [float(x.strip()) for x in dimensions.split(',')]
        if len(dims) != 2:
            raise ValueError()
    except ValueError:
        echo_error("Invalid dimensions format. Use 'x,y' (e.g., '8,8')")
        raise click.Abort()
    
    # Build electrode config
    electrode = ElectrodeConfig(
        shape=shape,
        dimensions=dims,
        thickness=thickness,
    )
    
    # Build intensity config
    intensity_config = IntensityConfig(
        pair1_ch1=intensity,
        pair1_ch2=intensity,
        pair2_ch1=intensity,
        pair2_ch2=intensity,
    )
    
    # Build parallel config
    parallel_config = ParallelConfig(
        enabled=parallel,
        max_workers=workers,
    )
    
    all_results = []
    start_time = time.time()
    
    for subject_id in subject:
        echo_info(f"Processing subject: {subject_id}")

        if dry_run:
            echo_info("Configuration:")
            click.echo(f"  EEG Net: {eeg_net}")
            click.echo(f"  Conductivity: {conductivity}")
            click.echo(f"  Intensity: {intensity} mA")
            click.echo(f"  Shape: {shape}, Dimensions: {dimensions}, Thickness: {thickness} mm")

        # Build simulation config
        config = SimulationConfig(
            subject_id=subject_id,
            project_dir=project_dir,
            conductivity_type=ConductivityType(conductivity),
            intensities=intensity_config,
            electrode=electrode,
            eeg_net=eeg_net,
            parallel=parallel_config,
        )

        # Load montages (skip expensive operations in dry-run mode)
        if dry_run:
            # In dry-run mode, create minimal mock montages without file I/O
            echo_info("Dry-run mode: Creating mock montages (skipping file I/O)")
            if montage:
                montages = [
                    MontageConfig(
                        name=m,
                        electrode_pairs=[(0, 0), (0, 0)],  # Dummy pairs
                        is_xyz=False,
                        eeg_net=eeg_net
                    ) for m in montage
                ]
                echo_success(f"Created {len(montages)} mock montage(s)")
            elif flex_file:
                # Create a mock flex montage
                montages = [
                    MontageConfig(
                        name="mock_flex_montage",
                        electrode_pairs=[(0, 0), (0, 0)],  # Dummy pairs
                        is_xyz=True,
                        eeg_net=eeg_net
                    )
                ]
                echo_success("Created 1 mock flex montage")
            else:
                echo_error("No montages specified. Use --montage or --flex-file")
                raise click.Abort()
        else:
            # Normal mode: load actual montages
            if flex_file:
                # Load from flex file
                flex_data = load_flex_montages(flex_file)
                montages = [parse_flex_montage(m) for m in flex_data]
            elif montage:
                montages = load_montages(
                    montage_names=list(montage),
                    project_dir=project_dir,
                    eeg_net=eeg_net,
                    include_flex=True,
                )
            else:
                echo_error("No montages specified. Use --montage or --flex-file")
                raise click.Abort()

        if not montages:
            echo_warning(f"No valid montages found for subject {subject_id}")
            continue

        # Setup logger with console output for integration tests/CI
        from tools import logging_util

        # Create log directory
        pm = get_path_manager()
        derivatives_dir = pm.get_derivatives_dir()
        log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_id}')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f'Simulator_{int(time.time())}.log')

        # Create logger with BOTH console and file output
        # This ensures SimNIBS output is visible in CircleCI/integration tests
        logger = logging_util.get_logger('TI-Simulator-CLI', log_file, overwrite=False, console=True)

        # Configure external loggers (SimNIBS) to also output to console and file
        logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct', 'TI'], logger)

        # Progress callback for console output
        def progress_callback(current, total, name):
            click.echo(f"  [{current+1}/{total}] {name}")

        # Run simulation
        try:
            if dry_run:
                echo_info(f"Dry run: Would simulate {len(montages)} montages for subject {subject_id}")
                # Create mock results for dry run
                results = [{
                    'subject_id': subject_id,
                    'montage_name': m.name if hasattr(m, 'name') else f'montage_{i}',
                    'status': 'completed',
                    'duration': 0.1
                } for i, m in enumerate(montages)]
            else:
                results = run_simulation(config, montages, logger=logger, progress_callback=progress_callback)
            all_results.extend(results)
            
            completed = sum(1 for r in results if r.get('status') == 'completed')
            failed = sum(1 for r in results if r.get('status') == 'failed')
            
            if failed == 0:
                echo_success(f"Subject {subject_id}: {completed} completed")
            else:
                echo_warning(f"Subject {subject_id}: {completed} completed, {failed} failed")
                
        except Exception as e:
            echo_error(f"Subject {subject_id} failed: {e}")
    
    # Summary
    elapsed = time.time() - start_time
    total_completed = sum(1 for r in all_results if r.get('status') == 'completed')
    total_failed = sum(1 for r in all_results if r.get('status') == 'failed')
    
    click.echo()
    echo_success(f"Completed: {total_completed}/{len(all_results)} simulations in {elapsed:.1f}s")
    
    # Exit with error code if any failed
    if total_failed > 0:
        sys.exit(1)


@cli.command('list-subjects')
@click.pass_context
def list_subjects_cmd(ctx):
    """List all available subjects in the project."""
    pm = ctx.obj['pm']
    
    if not pm.project_dir:
        echo_error("Project directory not set")
        raise click.Abort()
    
    subjects = pm.list_subjects()
    
    if not subjects:
        echo_warning("No subjects found")
        return
    
    echo_header("Available Subjects")
    display_subjects_table(subjects)
    click.echo()
    echo_info(f"Total: {len(subjects)} subject(s)")


@cli.command('list-montages')
@click.option('--subject', '-s', required=True, help='Subject ID')
@click.option('--eeg-net', '-e', required=True, help='EEG net file name')
@click.pass_context
def list_montages_cmd(ctx, subject, eeg_net):
    """List available montages for a subject."""
    project_dir = ctx.obj['project_dir']
    
    if not project_dir:
        echo_error("Project directory not set")
        raise click.Abort()
    
    try:
        montage_data = load_montage_file(project_dir, eeg_net)
    except (ValueError, FileNotFoundError) as e:
        echo_error(f"Failed to load montages: {e}")
        raise click.Abort()
    
    echo_header(f"Montages for {eeg_net}")
    
    for montage_type in ['uni_polar_montages', 'multi_polar_montages']:
        montages = montage_data.get(montage_type, {})
        if montages:
            echo_section(montage_type.replace('_', ' ').title())
            for name, pairs in montages.items():
                pairs_str = "; ".join([f"{p[0]},{p[1]}" for p in pairs])
                click.echo(f"  {name:<25} Pairs: {pairs_str}")


@cli.command('list-eeg-caps')
@click.option('--subject', '-s', required=True, help='Subject ID')
@click.pass_context
def list_eeg_caps_cmd(ctx, subject):
    """List available EEG caps for a subject."""
    pm = ctx.obj['pm']
    
    caps = pm.list_eeg_caps(subject)
    
    if not caps:
        echo_warning(f"No EEG caps found for subject {subject}")
        return
    
    echo_header(f"EEG Caps for Subject {subject}")
    for cap in caps:
        click.echo(f"  • {cap}")


@cli.command('list-simulations')
@click.option('--subject', '-s', required=True, help='Subject ID')
@click.pass_context
def list_simulations_cmd(ctx, subject):
    """List completed simulations for a subject."""
    pm = ctx.obj['pm']
    
    simulations = pm.list_simulations(subject)
    
    if not simulations:
        echo_warning(f"No simulations found for subject {subject}")
        return
    
    echo_header(f"Simulations for Subject {subject}")
    for sim in simulations:
        click.echo(f"  • {sim}")
    
    echo_info(f"Total: {len(simulations)} simulation(s)")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    cli(obj={})

