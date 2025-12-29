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

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import get_path_manager, list_subjects
from opt.ex import main as ex_main, get_full_config
from opt.leadfield import LeadfieldGenerator
from tools import logging_util


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


def prompt_roi_selection(subject_id: str) -> str:
    """Prompt user to select or create an ROI."""
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
            return prompt_new_roi()

        try:
            num = int(choice)
            if 1 <= num <= len(rois):
                return rois[num - 1]
        except ValueError:
            pass

        echo_error("Invalid selection")
        raise click.Abort()
    else:
        echo_warning("No existing ROIs found")
        return prompt_new_roi()


def prompt_new_roi() -> str:
    """Prompt user to create a new ROI."""
    roi_name = click.prompt(
        click.style("Enter ROI name", fg='white'),
        type=str
    )
    return roi_name


def list_available_leadfields(subject_id: str) -> List[Tuple[str, str, float]]:
    """List available leadfield files for a subject."""
    pm = get_path_manager()
    m2m_dir = pm.get_m2m_dir(subject_id)
    if not m2m_dir:
        return []

    gen = LeadfieldGenerator(m2m_dir)
    return gen.list_available_leadfields_hdf5(subject_id)


def prompt_leadfield_selection(subject_id: str) -> Optional[Tuple[str, str]]:
    """Prompt user to select, create, or both for leadfield."""
    leadfields = list_available_leadfields(subject_id)

    if leadfields:
        echo_section(f"Available Leadfields for Subject {subject_id}")
        for i, (net_name, hdf5_path, size_gb) in enumerate(leadfields, 1):
            click.echo(f"{i:3d}. {net_name:<30} ({size_gb:.2f} GB)")

        click.echo()
        click.echo("Options:")
        click.echo("  [number] - Use existing leadfield")
        click.echo("  new      - Create new leadfield")
        click.echo("  both     - Create new, then select")

        choice = click.prompt(
            click.style("Your choice", fg='white'),
            type=str,
            default='1'
        )

        if choice.lower() == 'new':
            return create_new_leadfield(subject_id)
        elif choice.lower() == 'both':
            create_new_leadfield(subject_id)
            # Refresh list and prompt again
            leadfields = list_available_leadfields(subject_id)
            return prompt_existing_leadfield(subject_id, leadfields)
        else:
            try:
                num = int(choice)
                if 1 <= num <= len(leadfields):
                    net_name, hdf5_path, _ = leadfields[num - 1]
                    echo_success(f"Selected leadfield: {net_name}")
                    return (net_name, hdf5_path)
            except ValueError:
                pass

            echo_error("Invalid selection")
            raise click.Abort()
    else:
        echo_warning("No existing leadfields found")
        return create_new_leadfield(subject_id)


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


def create_new_leadfield(subject_id: str) -> Tuple[str, str]:
    """Create a new leadfield for a subject."""
    pm = get_path_manager()
    m2m_dir = pm.get_m2m_dir(subject_id)

    if not m2m_dir:
        echo_error(f"M2M directory not found for subject {subject_id}")
        raise click.Abort()

    # List available EEG caps
    eeg_caps = pm.list_eeg_caps(subject_id)
    if not eeg_caps:
        echo_error(f"No EEG caps found for subject {subject_id}")
        raise click.Abort()

    echo_section("Available EEG Caps")
    for i, cap in enumerate(eeg_caps, 1):
        click.echo(f"{i:3d}. {cap}")

    choice = click.prompt(
        click.style("Select EEG cap", fg='white'),
        type=click.IntRange(1, len(eeg_caps)),
        default=1
    )

    selected_cap = eeg_caps[choice - 1]
    net_name = selected_cap.replace('.csv', '')

    echo_info(f"Creating leadfield for {net_name}...")

    # Get paths
    eeg_cap_path = os.path.join(pm.get_eeg_positions_dir(subject_id), selected_cap)
    leadfield_dir = pm.get_leadfield_dir(subject_id)

    # Create leadfield generator
    gen = LeadfieldGenerator(m2m_dir, electrode_cap=net_name)

    try:
        result = gen.generate_leadfield(
            output_dir=leadfield_dir,
            tissues=[1, 2],  # GM and WM
            eeg_cap_path=eeg_cap_path
        )
        hdf5_path = result['hdf5']
        echo_success(f"Leadfield created: {hdf5_path}")
        return (net_name, hdf5_path)
    except Exception as e:
        echo_error(f"Failed to create leadfield: {e}")
        raise


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
) -> bool:
    """Show configuration summary and get confirmation."""
    echo_header("Configuration Summary")

    echo_section("Subjects")
    for subj in subjects:
        click.echo(f"  • {subj}")

    echo_section("Optimization Parameters")
    click.echo(f"  ROI:           {roi_name}")
    click.echo(f"  EEG Net:       {net_name}")
    click.echo(f"  Mode:          {'All Combinations' if all_combinations else 'Bucketed'}")

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
@click.option('--all-combinations', is_flag=True,
              help='Use all combinations mode (vs bucketed mode)')
@click.pass_context
def interactive(ctx, all_combinations):
    """Run ex-search in interactive mode."""
    pm = ctx.obj['pm']
    project_dir = ctx.obj['project_dir']

    if not project_dir:
        echo_error("Project directory not set. Use --project-dir or set PROJECT_DIR environment variable.")
        raise click.Abort()

    # Welcome
    echo_header("TI-Toolbox Ex-Search Optimization")
    click.echo(f"Project: {project_dir}")
    click.echo(f"Mode: {'All Combinations' if all_combinations else 'Bucketed'}")

    # Get available subjects
    subjects = list_subjects()
    if not subjects:
        echo_error("No subjects found in project directory")
        raise click.Abort()

    # Interactive prompts
    selected_subjects = prompt_subjects(subjects)

    # Process each subject
    for subject_id in selected_subjects:
        click.echo()
        echo_info(f"Processing subject: {subject_id}")

        # ROI selection/creation
        roi_name = prompt_roi_selection(subject_id)
        echo_success(f"ROI: {roi_name}")

        # Leadfield selection/creation
        net_name, hdf5_path = prompt_leadfield_selection(subject_id)
        echo_success(f"Leadfield: {net_name}")

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
            project_dir=project_dir,
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
@click.option('--all-combinations', is_flag=True,
              help='Use all combinations mode')
@click.pass_context
def run(ctx, subject, roi_name, net_name, leadfield_hdf, total_current,
        current_step, channel_limit, all_combinations):
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
    echo_info(f"ROI: {roi_name}")
    echo_info(f"EEG Net: {net_name}")
    echo_info(f"Current: {total_current} mA (step: {current_step} mA, limit: {channel_limit} mA)")

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
        project_dir=project_dir,
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
    project_dir: str,
):
    """Execute ex-search optimization for a subject."""
    echo_header("Running Ex-Search Optimization")

    # Set environment variables for ex-search main
    os.environ['PROJECT_DIR'] = project_dir
    os.environ['SUBJECT_NAME'] = subject_id
    os.environ['SELECTED_EEG_NET'] = net_name
    os.environ['LEADFIELD_HDF'] = hdf5_path
    os.environ['ROI_NAME'] = roi_name
    os.environ['TOTAL_CURRENT'] = str(total_current)
    os.environ['CURRENT_STEP'] = str(current_step)
    os.environ['CHANNEL_LIMIT'] = str(channel_limit)

    # Create logger
    pm = get_path_manager()
    derivatives_dir = pm.get_derivatives_dir()
    log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_id}')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'ExSearch_{int(time.time())}.log')
    os.environ['TI_LOG_FILE'] = log_file

    start_time = time.time()

    try:
        # Run ex-search main
        ex_main.main()

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
