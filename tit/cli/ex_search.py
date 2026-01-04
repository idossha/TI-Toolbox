#!/usr/bin/env python3
"""
TI-Toolbox Ex-Search CLI

A Click-based command-line interface for running exhaustive search optimization.
Provides both interactive and direct execution modes.

Usage:
    # Interactive mode
    python ex_search.py

    # Direct mode (for GUI/scripting)
    python ex_search.py run --subject 101 --roi-name M1_left --total-current 1.0

    # List available subjects
    python ex_search.py list-subjects

    # List available leadfields
    python ex_search.py list-leadfields --subject 101
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import click

from tit.core import get_path_manager, list_subjects
from tit import logger as logging_util
from tit.cli import utils as cli_utils

# =============================================================================
# STYLING HELPERS
# =============================================================================

COLORS = cli_utils.COLORS
echo_header = cli_utils.echo_header
echo_section = cli_utils.echo_section
echo_success = cli_utils.echo_success
echo_warning = cli_utils.echo_warning
echo_error = cli_utils.echo_error
echo_info = cli_utils.echo_info


# =============================================================================
# INTERACTIVE PROMPTS
# =============================================================================

def display_subjects_table(subjects: List[str]) -> None:
    cli_utils.display_table(subjects)


def prompt_subjects(subjects: List[str]) -> List[str]:
    return cli_utils.prompt_subject_ids(subjects)


def list_available_rois(subject_id: str) -> List[str]:
    """List available ROIs for a subject."""
    pm = get_path_manager()
    m2m_dir = pm.get_m2m_dir(subject_id)
    if not m2m_dir:
        return []

    roi_dir = os.path.join(m2m_dir, "ROIs")
    if not os.path.exists(roi_dir):
        return []

    rois = []
    for f in os.listdir(roi_dir):
        if f.endswith('.csv') and f != 'roi_list.txt':
            rois.append(f.replace('.csv', ''))

    return sorted(rois)


def prompt_roi_selection(subject_id: str) -> Tuple[str, float]:
    """Prompt user to select or create an ROI. Returns (roi_name, radius)."""
    rois = list_available_rois(subject_id)

    if rois:
        echo_section(f"Available ROIs for Subject {subject_id}")
        for i, roi in enumerate(rois, 1):
            click.echo(f"{i:3d}. {roi}")

        click.echo()
        choice = click.prompt(
            click.style("Select ROI number (or 'new' to create new)", fg='white'),
            type=str
        )

        if choice.lower() == 'new':
            roi_name, sphere_radius, center_coords = prompt_new_roi()
            create_roi_csv(subject_id, roi_name, center_coords)
            return roi_name, sphere_radius

        try:
            num = int(choice)
            if 1 <= num <= len(rois):
                roi_name = rois[num - 1]
                # For existing ROIs, prompt for radius to use
                sphere_radius = click.prompt(
                    click.style(f"Radius for ROI '{roi_name}' (mm)", fg='white'),
                    type=float,
                    default=10.0
                )
                return roi_name, sphere_radius
        except ValueError:
            pass

        echo_error("Invalid selection")
        raise click.Abort()
    else:
        echo_warning("No existing ROIs found")
        roi_name, sphere_radius, center_coords = prompt_new_roi()
        create_roi_csv(subject_id, roi_name, center_coords)
        return roi_name, sphere_radius


def prompt_new_roi() -> Tuple[str, float]:
    """Prompt user to create a new ROI."""
    roi_name = click.prompt(
        click.style("Enter ROI name", fg='white'),
        type=str
    )

    # Prompt for center coordinates
    click.echo()
    click.echo("Enter sphere center coordinates (in mm):")
    center_x = click.prompt(
        click.style("Center X coordinate", fg='white'),
        type=float,
        default=0.0
    )
    center_y = click.prompt(
        click.style("Center Y coordinate", fg='white'),
        type=float,
        default=0.0
    )
    center_z = click.prompt(
        click.style("Center Z coordinate", fg='white'),
        type=float,
        default=0.0
    )

    # Prompt for sphere radius
    sphere_radius = click.prompt(
        click.style("Sphere radius (mm)", fg='white'),
        type=float,
        default=10.0
    )

    return roi_name, sphere_radius, [center_x, center_y, center_z]


def create_roi_csv(subject_id: str, roi_name: str, center_coords: List[float]) -> str:
    """Create a new ROI CSV file with the given center coordinates."""
    from tit.core.roi import ROICoordinateHelper

    pm = get_path_manager()
    roi_dir = os.path.join(pm.get_m2m_dir(subject_id), 'ROIs')
    os.makedirs(roi_dir, exist_ok=True)

    roi_file_path = os.path.join(roi_dir, f"{roi_name}.csv")

    # Save the coordinates to CSV
    ROICoordinateHelper.save_roi_to_csv(center_coords, roi_file_path)

    echo_success(f"Created ROI file: {roi_file_path}")
    echo_info(f"Center coordinates: [{center_coords[0]}, {center_coords[1]}, {center_coords[2]}] mm")

    return roi_file_path


def list_available_leadfields(subject_id: str) -> List[Tuple[str, str, float]]:
    """List available leadfield files for a subject."""
    from tit.opt.leadfield import LeadfieldGenerator

    pm = get_path_manager()
    m2m_dir = pm.get_m2m_dir(subject_id)
    if not m2m_dir:
        return []

    gen = LeadfieldGenerator(m2m_dir)
    return gen.list_available_leadfields_hdf5(subject_id)


def prompt_leadfield_selection(subject_id: str) -> Optional[Tuple[str, str]]:
    """Prompt user to select an existing leadfield."""
    leadfields = list_available_leadfields(subject_id)

    if leadfields:
        echo_section(f"Available Leadfields for Subject {subject_id}")
        for i, (net_name, hdf5_path, size_gb) in enumerate(leadfields, 1):
            click.echo(f"{i:3d}. {net_name:<30} ({size_gb:.2f} GB)")

        click.echo()

        choice = click.prompt(
            click.style("Select leadfield number", fg='white'),
            type=click.IntRange(1, len(leadfields)),
            default=1
        )

        net_name, hdf5_path, _ = leadfields[choice - 1]
        echo_success(f"Selected leadfield: {net_name}")
        return (net_name, hdf5_path)
    else:
        echo_error("No existing leadfields found")
        echo_info("Use 'tit create-leadfield' command to create leadfields first")
        raise click.Abort()


def prompt_existing_leadfield(subject_id: str, leadfields: List[Tuple[str, str, float]]) -> Tuple[str, str]:
    """Prompt to select from existing leadfields."""
    echo_section(f"Available Leadfields for Subject {subject_id}")
    for i, (net_name, hdf5_path, size_gb) in enumerate(leadfields, 1):
        click.echo(f"{i:3d}. {net_name:<30} ({size_gb:.2f} GB)")

    choice = click.prompt(
        click.style("Select leadfield number", fg='white'),
        type=click.IntRange(1, len(leadfields)),
        default=1
    )

    net_name, hdf5_path, _ = leadfields[choice - 1]
    echo_success(f"Selected leadfield: {net_name}")
    return (net_name, hdf5_path)




def prompt_optimization_mode() -> bool:
    """Prompt user to select optimization mode (bucketed vs all combinations)."""
    echo_section("Optimization Mode")
    click.echo("1. Bucketed mode (E1+/-, E2+/- channels)")
    click.echo("   - Electrodes grouped into specific channels")
    click.echo("   - Faster optimization with structured electrode assignment")
    click.echo()
    click.echo("2. All Combinations mode (pooled electrodes)")
    click.echo("   - All electrodes in a single pool")
    click.echo("   - Exhaustive search across all possible combinations")
    click.echo("   - Slower but more thorough")
    click.echo()

    choice = click.prompt(
        click.style("Select mode (1=Bucketed, 2=All Combinations)", fg='white'),
        type=click.IntRange(1, 2),
        default=1
    )

    return choice == 2  # True if All Combinations, False if Bucketed


def get_available_electrodes(subject_id: str, net_name: str) -> List[str]:
    """Get list of available electrodes from EEG cap."""
    from tit.opt.leadfield import LeadfieldGenerator

    pm = get_path_manager()
    m2m_dir = pm.get_m2m_dir(subject_id)
    if not m2m_dir:
        return []

    # Clean cap name (remove .csv extension if present)
    clean_cap_name = net_name.replace('.csv', '') if net_name.endswith('.csv') else net_name

    try:
        # Create LeadfieldGenerator instance to use its methods
        gen = LeadfieldGenerator(m2m_dir)

        # Use the generator's method to get electrode names, which will handle cap file finding
        electrodes = gen.get_electrode_names_from_cap(cap_name=clean_cap_name)
        return electrodes
    except FileNotFoundError:
        echo_warning(f"Could not load electrodes from {clean_cap_name}.csv, continuing without validation")
        return []


def prompt_electrodes_bucketed(available_electrodes: List[str]) -> dict:
    """Prompt user to select electrodes in bucketed mode (E1+/-, E2+/-)."""
    echo_section("Electrode Selection - Bucketed Mode")
    click.echo("Select electrodes for each channel:")
    click.echo("(Enter electrode names separated by spaces or commas)")
    click.echo()

    if available_electrodes:
        click.echo(f"Available electrodes ({len(available_electrodes)}): {', '.join(available_electrodes[:20])}")
        if len(available_electrodes) > 20:
            click.echo(f"... and {len(available_electrodes) - 20} more")
        click.echo()

    def get_electrode_list(prompt_text):
        while True:
            selection = click.prompt(
                click.style(prompt_text, fg='white'),
                type=str
            )
            electrodes = selection.replace(',', ' ').split()
            if electrodes:
                return electrodes
            echo_warning("Please enter at least one electrode")

    e1_plus = get_electrode_list("E1+ electrodes")
    e1_minus = get_electrode_list("E1- electrodes")
    e2_plus = get_electrode_list("E2+ electrodes")
    e2_minus = get_electrode_list("E2- electrodes")

    return {
        'E1_plus': e1_plus,
        'E1_minus': e1_minus,
        'E2_plus': e2_plus,
        'E2_minus': e2_minus,
    }


def prompt_electrodes_pooled(available_electrodes: List[str]) -> dict:
    """Prompt user to select electrodes in pooled/all-combinations mode."""
    echo_section("Electrode Selection - All Combinations Mode")
    click.echo("Select electrodes for the optimization pool:")
    click.echo("(All selected electrodes will be tested in all possible combinations)")
    click.echo()

    if available_electrodes:
        click.echo(f"Available electrodes ({len(available_electrodes)}): {', '.join(available_electrodes[:20])}")
        if len(available_electrodes) > 20:
            click.echo(f"... and {len(available_electrodes) - 20} more")
        click.echo()

    while True:
        selection = click.prompt(
            click.style("All electrodes (space/comma separated)", fg='white'),
            type=str
        )
        electrodes = selection.replace(',', ' ').split()
        if len(electrodes) >= 4:
            # In all combinations mode, all channels use the same electrode pool
            return {
                'E1_plus': electrodes,
                'E1_minus': electrodes,
                'E2_plus': electrodes,
                'E2_minus': electrodes,
            }
        echo_warning("Please enter at least 4 electrodes for all-combinations mode")


def prompt_current_parameters() -> Tuple[float, float, float]:
    """Prompt user for current configuration parameters."""
    echo_section("Current Configuration")
    click.echo("Configure current parameters for optimization")
    click.echo()

    total_current = click.prompt(
        click.style("Total current (mA)", fg='white'),
        type=float,
        default=1.0
    )

    current_step = click.prompt(
        click.style("Current step size (mA)", fg='white'),
        type=float,
        default=0.1
    )

    default_limit = total_current / 2.0
    channel_limit = click.prompt(
        click.style("Channel limit (mA)", fg='white'),
        type=float,
        default=default_limit
    )

    return (total_current, current_step, channel_limit)


def show_confirmation(
    subjects: List[str],
    roi_name: str,
    net_name: str,
    total_current: float,
    current_step: float,
    channel_limit: float,
    all_combinations: bool,
    electrodes: dict,
    roi_radius: float,
) -> bool:
    """Show configuration summary and get confirmation."""
    echo_header("Configuration Summary")

    echo_section("Subjects")
    for subj in subjects:
        click.echo(f"  • {subj}")

    echo_section("Optimization Parameters")
    click.echo(f"  ROI:           {roi_name}")
    click.echo(f"  ROI Radius:    {roi_radius} mm")
    click.echo(f"  EEG Net:       {net_name}")
    click.echo(f"  Mode:          {'All Combinations' if all_combinations else 'Bucketed'}")

    echo_section("Electrode Configuration")
    if all_combinations:
        click.echo(f"  Pool:          {', '.join(electrodes['E1_plus'])}")
    else:
        click.echo(f"  E1+:           {', '.join(electrodes['E1_plus'])}")
        click.echo(f"  E1-:           {', '.join(electrodes['E1_minus'])}")
        click.echo(f"  E2+:           {', '.join(electrodes['E2_plus'])}")
        click.echo(f"  E2-:           {', '.join(electrodes['E2_minus'])}")

    echo_section("Current Configuration")
    click.echo(f"  Total:         {total_current} mA")
    click.echo(f"  Step:          {current_step} mA")
    click.echo(f"  Channel Limit: {channel_limit} mA")

    click.echo()
    return click.confirm(
        click.style("Proceed with ex-search optimization?", fg='yellow', bold=True),
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
    TI-Toolbox Ex-Search CLI

    Run exhaustive search optimization interactively or via command-line options.
    """
    ctx.ensure_object(dict)

    # Initialize path manager
    pm = get_path_manager()
    pm.project_dir = project_dir

    ctx.obj['pm'] = pm
    ctx.obj['project_dir'] = pm.project_dir

    # If no subcommand, run interactive mode
    if ctx.invoked_subcommand is None:
        ctx.invoke(interactive)


@cli.command()
@click.pass_context
def interactive(ctx):
    """Run ex-search in interactive mode."""
    pm = ctx.obj['pm']
    project_dir = ctx.obj['project_dir']

    if not project_dir:
        echo_error("Project directory not set. Use --project-dir or set PROJECT_DIR environment variable.")
        raise click.Abort()

    # Welcome
    echo_header("TI-Toolbox Ex-Search Optimization")
    click.echo(f"Project: {project_dir}")

    # Get available subjects
    subjects = list_subjects()
    if not subjects:
        echo_error("No subjects found in project directory")
        raise click.Abort()

    # Interactive prompts
    selected_subjects = prompt_subjects(subjects)

    # Prompt for optimization mode BEFORE electrode selection
    all_combinations = prompt_optimization_mode()
    echo_success(f"Mode: {'All Combinations (pooled)' if all_combinations else 'Bucketed (E1+/-, E2+/-)'}")

    # Process each subject
    for subject_id in selected_subjects:
        click.echo()
        echo_info(f"Processing subject: {subject_id}")

        # ROI selection/creation
        roi_name, roi_radius = prompt_roi_selection(subject_id)
        echo_success(f"ROI: {roi_name} (radius: {roi_radius} mm)")

        # Leadfield selection/creation
        net_name, hdf5_path = prompt_leadfield_selection(subject_id)
        echo_success(f"Leadfield: {net_name}")

        # Get available electrodes
        available_electrodes = get_available_electrodes(subject_id, net_name)
        if not available_electrodes:
            echo_warning(f"Could not load electrodes from {net_name}.csv, continuing without validation")

        # Electrode selection based on mode
        if all_combinations:
            electrodes = prompt_electrodes_pooled(available_electrodes)
        else:
            electrodes = prompt_electrodes_bucketed(available_electrodes)

        echo_success(f"Electrodes configured: {len(electrodes['E1_plus'])} electrode(s)")

        # Current parameters
        total_current, current_step, channel_limit = prompt_current_parameters()

        # Confirmation
        if not show_confirmation(
            subjects=[subject_id],
            roi_name=roi_name,
            net_name=net_name,
            total_current=total_current,
            current_step=current_step,
            channel_limit=channel_limit,
            all_combinations=all_combinations,
            electrodes=electrodes,
            roi_radius=roi_radius,
        ):
            echo_warning("Ex-search cancelled")
            continue

        # Run ex-search
        run_ex_search(
            subject_id=subject_id,
            roi_name=roi_name,
            net_name=net_name,
            hdf5_path=hdf5_path,
            total_current=total_current,
            current_step=current_step,
            channel_limit=channel_limit,
            all_combinations=all_combinations,
            electrodes=electrodes,
            project_dir=project_dir,
            roi_radius=roi_radius,
        )


@cli.command()
@click.option('--subject', '-s', required=True,
              help='Subject ID to process')
@click.option('--roi-name', '-r', required=True,
              help='ROI name for optimization')
@click.option('--net-name', '-n',
              help='EEG net name (will prompt if not provided)')
@click.option('--leadfield-hdf', '-l',
              help='Path to leadfield HDF5 file (will prompt if not provided)')
@click.option('--total-current', '-t', type=float, default=1.0,
              help='Total current in mA')
@click.option('--current-step', type=float, default=0.1,
              help='Current step size in mA')
@click.option('--channel-limit', type=float,
              help='Channel limit in mA (default: total_current/2)')
@click.option('--roi-radius', type=float, default=10.0,
              help='ROI sphere radius in mm')
@click.option('--all-combinations', is_flag=True,
              help='Use all combinations mode')
@click.option('--electrodes', '-e', multiple=True,
              help='Electrodes (for all-combinations mode, specify once with all electrodes; for bucketed mode, specify 4 times: E1+, E1-, E2+, E2-)')
@click.pass_context
def run(ctx, subject, roi_name, net_name, leadfield_hdf, total_current,
        current_step, channel_limit, all_combinations, electrodes, roi_radius):
    """
    Run ex-search directly with command-line options.

    This is the non-interactive mode for scripting and GUI integration.
    """
    pm = ctx.obj['pm']
    project_dir = ctx.obj['project_dir']

    if not project_dir:
        echo_error("Project directory not set")
        raise click.Abort()

    # Verify subject exists
    m2m_dir = pm.get_m2m_dir(subject)
    if not m2m_dir:
        echo_error(f"Subject not found: {subject}")
        raise click.Abort()

    # Handle leadfield selection if not provided
    if not leadfield_hdf:
        leadfields = list_available_leadfields(subject)
        if not leadfields:
            echo_error(f"No leadfields found for subject {subject}")
            echo_info("Use create-leadfield command to create one first")
            raise click.Abort()

        # Use first leadfield by default
        net_name, leadfield_hdf, _ = leadfields[0]
        echo_info(f"Using leadfield: {net_name}")

    # Set channel limit default
    if channel_limit is None:
        channel_limit = total_current / 2.0

    # Extract net_name from leadfield if not provided
    if not net_name:
        # Try to extract from leadfield filename
        net_name = os.path.basename(leadfield_hdf).replace('_leadfield.hdf5', '')
        if not net_name:
            net_name = "unknown"

    echo_info(f"Processing subject: {subject}")
    echo_info(f"ROI: {roi_name} (radius: {roi_radius} mm)")
    echo_info(f"EEG Net: {net_name}")
    echo_info(f"Current: {total_current} mA (step: {current_step} mA, limit: {channel_limit} mA)")

    # Parse electrodes parameter
    if electrodes:
        if all_combinations:
            # All electrodes go into the pool
            electrode_list = ' '.join(electrodes).replace(',', ' ').split()
            electrodes_dict = {
                'E1_plus': electrode_list,
                'E1_minus': electrode_list,
                'E2_plus': electrode_list,
                'E2_minus': electrode_list,
            }
            echo_info(f"Electrodes (pool): {', '.join(electrode_list)}")
        else:
            # Bucketed mode: expect 4 electrode groups
            if len(electrodes) != 4:
                echo_error("Bucketed mode requires 4 electrode groups: E1+, E1-, E2+, E2-")
                echo_info("Example: --electrodes 'E1 E2' --electrodes 'E3 E4' --electrodes 'E5 E6' --electrodes 'E7 E8'")
                raise click.Abort()

            electrodes_dict = {
                'E1_plus': electrodes[0].replace(',', ' ').split(),
                'E1_minus': electrodes[1].replace(',', ' ').split(),
                'E2_plus': electrodes[2].replace(',', ' ').split(),
                'E2_minus': electrodes[3].replace(',', ' ').split(),
            }
            echo_info(f"E1+: {', '.join(electrodes_dict['E1_plus'])}")
            echo_info(f"E1-: {', '.join(electrodes_dict['E1_minus'])}")
            echo_info(f"E2+: {', '.join(electrodes_dict['E2_plus'])}")
            echo_info(f"E2-: {', '.join(electrodes_dict['E2_minus'])}")
    else:
        # No electrodes provided - ex-search config will prompt
        echo_warning("No electrodes specified. Ex-search will prompt for electrode input.")
        electrodes_dict = {
            'E1_plus': [],
            'E1_minus': [],
            'E2_plus': [],
            'E2_minus': [],
        }

    # Run ex-search
    run_ex_search(
        subject_id=subject,
        roi_name=roi_name,
        net_name=net_name,
        hdf5_path=leadfield_hdf,
        total_current=total_current,
        current_step=current_step,
        channel_limit=channel_limit,
        all_combinations=all_combinations,
        electrodes=electrodes_dict,
        project_dir=project_dir,
        roi_radius=roi_radius,
    )


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


@cli.command('list-leadfields')
@click.option('--subject', '-s', required=True, help='Subject ID')
@click.pass_context
def list_leadfields_cmd(ctx, subject):
    """List available leadfields for a subject."""
    pm = ctx.obj['pm']

    leadfields = list_available_leadfields(subject)

    if not leadfields:
        echo_warning(f"No leadfields found for subject {subject}")
        return

    echo_header(f"Leadfields for Subject {subject}")
    for net_name, hdf5_path, size_gb in leadfields:
        click.echo(f"  {net_name:<30} ({size_gb:.2f} GB)")
        click.echo(f"    Path: {hdf5_path}")

    echo_info(f"Total: {len(leadfields)} leadfield(s)")


@cli.command('list-rois')
@click.option('--subject', '-s', required=True, help='Subject ID')
@click.pass_context
def list_rois_cmd(ctx, subject):
    """List available ROIs for a subject."""
    rois = list_available_rois(subject)

    if not rois:
        echo_warning(f"No ROIs found for subject {subject}")
        return

    echo_header(f"ROIs for Subject {subject}")
    for roi in rois:
        click.echo(f"  • {roi}")

    echo_info(f"Total: {len(rois)} ROI(s)")


# =============================================================================
# EXECUTION LOGIC
# =============================================================================

def run_ex_search(
    subject_id: str,
    roi_name: str,
    net_name: str,
    hdf5_path: str,
    total_current: float,
    current_step: float,
    channel_limit: float,
    all_combinations: bool,
    electrodes: dict,
    project_dir: str,
    roi_radius: float = 3.0,
):
    """Execute ex-search optimization for a subject."""
    from tit.opt.ex import main as ex_main

    echo_header("Running Ex-Search Optimization")

    # Set environment variables for ex-search main
    os.environ['PROJECT_DIR'] = project_dir
    os.environ['SUBJECT_NAME'] = subject_id
    os.environ['SELECTED_EEG_NET'] = net_name
    os.environ['LEADFIELD_HDF'] = hdf5_path
    os.environ['ROI_NAME'] = roi_name
    os.environ['ROI_RADIUS'] = str(roi_radius)
    os.environ['TOTAL_CURRENT'] = str(total_current)
    os.environ['CURRENT_STEP'] = str(current_step)
    os.environ['CHANNEL_LIMIT'] = str(channel_limit)

    # Set electrode environment variables (space-separated) if provided
    if electrodes['E1_plus']:
        os.environ['E1_PLUS'] = ' '.join(electrodes['E1_plus'])
    if electrodes['E1_minus']:
        os.environ['E1_MINUS'] = ' '.join(electrodes['E1_minus'])
    if electrodes['E2_plus']:
        os.environ['E2_PLUS'] = ' '.join(electrodes['E2_plus'])
    if electrodes['E2_minus']:
        os.environ['E2_MINUS'] = ' '.join(electrodes['E2_minus'])
    os.environ['ALL_COMBINATIONS'] = '1' if all_combinations else '0'

    # Create logger
    pm = get_path_manager()
    derivatives_dir = pm.get_derivatives_dir()
    log_dir = os.path.join(derivatives_dir, 'tit', 'logs', f'sub-{subject_id}')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'ExSearch_{int(time.time())}.log')
    os.environ['TI_LOG_FILE'] = log_file

    start_time = time.time()

    try:
        # Run ex-search main (ex_main IS the main function)
        ex_main()

        elapsed = time.time() - start_time
        echo_success(f"Ex-search completed in {elapsed/60:.1f} minutes")
        echo_info(f"Log file: {log_file}")

    except Exception as e:
        echo_error(f"Ex-search failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    cli(obj={})
