#!/usr/bin/env python3
"""
TI-Toolbox Leadfield Builder CLI

A Click-based command-line interface for creating leadfield matrices.
Provides both interactive and direct execution modes.

Usage:
    # Interactive mode
    python create_leadfield.py

    # Direct mode (for GUI/scripting)
    python create_leadfield.py build --subject 101 --eeg-net GSN-HydroCel-185

    # List available subjects
    python create_leadfield.py list-subjects

    # List available EEG caps for a subject
    python create_leadfield.py list-caps --subject 101

    # List existing leadfields
    python create_leadfield.py list-leadfields --subject 101
"""

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


def list_available_caps(subject_id: str) -> List[str]:
    """List available EEG caps for a subject."""
    pm = get_path_manager()
    caps = pm.list_eeg_caps(subject_id)
    return caps if caps else []


def prompt_eeg_caps(subject_id: str) -> List[str]:
    """Prompt user to select EEG caps for leadfield generation."""
    caps = list_available_caps(subject_id)

    if not caps:
        echo_error(f"No EEG caps found for subject {subject_id}")
        raise click.Abort()

    echo_section(f"Available EEG Caps for Subject {subject_id}")
    for i, cap in enumerate(caps, 1):
        click.echo(f"{i:3d}. {cap}")

    click.echo()
    click.echo("Options:")
    click.echo("  [numbers] - Select specific caps (e.g., 1,2,3)")
    click.echo("  all       - Generate for all caps")

    selection = click.prompt(
        click.style("Your choice", fg='white'),
        type=str,
        default='1'
    )

    if selection.lower() == 'all':
        return caps

    selected = []
    for num_str in selection.split(','):
        try:
            num = int(num_str.strip())
            if 1 <= num <= len(caps):
                selected.append(caps[num - 1])
            else:
                echo_warning(f"Invalid number: {num}")
        except ValueError:
            echo_warning(f"Invalid input: {num_str}")

    if not selected:
        echo_error("No valid caps selected")
        raise click.Abort()

    return selected


def list_existing_leadfields(subject_id: str) -> List[Tuple[str, str, float]]:
    """List existing leadfields for a subject."""
    from tit.opt.leadfield import LeadfieldGenerator

    pm = get_path_manager()
    m2m_dir = pm.get_m2m_dir(subject_id)
    if not m2m_dir:
        return []

    gen = LeadfieldGenerator(m2m_dir)
    return gen.list_available_leadfields_hdf5(subject_id)


def show_confirmation(
    subjects: List[str],
    caps_per_subject: dict,
    tissues: List[int],
) -> bool:
    """Show configuration summary and get confirmation."""
    echo_header("Leadfield Generation Summary")

    total_leadfields = sum(len(caps) for caps in caps_per_subject.values())

    echo_section("Configuration")
    click.echo(f"  Subjects:  {len(subjects)}")
    click.echo(f"  Total leadfields to generate: {total_leadfields}")
    click.echo(f"  Tissues:   {tissues} (1=GM, 2=WM)")

    echo_section("Details")
    for subject_id, caps in caps_per_subject.items():
        click.echo(f"\n  {subject_id}:")
        for cap in caps:
            net_name = cap.replace('.csv', '')
            click.echo(f"    • {net_name}")

    click.echo()
    echo_warning("Note: Each leadfield generation may take 10-30 minutes depending on mesh size")
    click.echo()

    return click.confirm(
        click.style("Proceed with leadfield generation?", fg='yellow', bold=True),
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
    TI-Toolbox Leadfield Builder CLI

    Create leadfield matrices for subjects with specified EEG nets.
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
@click.option('--tissues', '-t', multiple=True, type=int,
              help='Tissue types (1=GM, 2=WM). Can specify multiple times.')
@click.pass_context
def interactive(ctx, tissues):
    """Run leadfield builder in interactive mode."""
    pm = ctx.obj['pm']
    project_dir = ctx.obj['project_dir']

    if not project_dir:
        echo_error("Project directory not set. Use --project-dir or set PROJECT_DIR environment variable.")
        raise click.Abort()

    # Welcome
    echo_header("TI-Toolbox Leadfield Builder")
    click.echo(f"Project: {project_dir}")

    # Default tissues
    if not tissues:
        tissues = [1, 2]  # GM and WM
    else:
        tissues = list(tissues)

    # Get available subjects
    subjects = list_subjects()
    if not subjects:
        echo_error("No subjects found in project directory")
        raise click.Abort()

    # Interactive prompts
    selected_subjects = prompt_subjects(subjects)

    # Collect EEG caps for each subject
    caps_per_subject = {}
    for subject_id in selected_subjects:
        selected_caps = prompt_eeg_caps(subject_id)
        caps_per_subject[subject_id] = selected_caps
        echo_success(f"Subject {subject_id}: {len(selected_caps)} cap(s) selected")

    # Show existing leadfields
    click.echo()
    echo_section("Existing Leadfields")
    for subject_id in selected_subjects:
        existing = list_existing_leadfields(subject_id)
        if existing:
            click.echo(f"\n  {subject_id}:")
            for net_name, hdf5_path, size_gb in existing:
                click.echo(f"    • {net_name} ({size_gb:.2f} GB)")
        else:
            click.echo(f"\n  {subject_id}: No existing leadfields")

    # Confirmation
    if not show_confirmation(selected_subjects, caps_per_subject, tissues):
        echo_warning("Leadfield generation cancelled")
        raise click.Abort()

    # Generate leadfields
    echo_header("Generating Leadfields")
    total_generated = 0
    total_failed = 0

    for subject_id in selected_subjects:
        caps = caps_per_subject[subject_id]
        echo_info(f"\nProcessing subject: {subject_id} ({len(caps)} leadfield(s))")

        for cap in caps:
            net_name = cap.replace('.csv', '')
            echo_info(f"  Generating leadfield for: {net_name}")

            result = build_leadfield_for_subject(
                subject_id=subject_id,
                eeg_cap=cap,
                tissues=tissues,
                pm=pm,
            )

            if result:
                total_generated += 1
                echo_success(f"  ✓ {net_name} completed")
            else:
                total_failed += 1
                echo_error(f"  ✗ {net_name} failed")

    # Summary
    echo_header("Generation Complete")
    click.echo(f"Total generated: {total_generated}")
    click.echo(f"Total failed: {total_failed}")


@cli.command()
@click.option('--subject', '-s', required=True, multiple=True,
              help='Subject ID(s) to process')
@click.option('--eeg-net', '-e', required=True, multiple=True,
              help='EEG net name(s) (e.g., GSN-HydroCel-185)')
@click.option('--tissues', '-t', multiple=True, type=int, default=[1, 2],
              help='Tissue types (1=GM, 2=WM)')
@click.option('--cleanup/--no-cleanup', default=True,
              help='Clean up old simulation files before running')
@click.pass_context
def build(ctx, subject, eeg_net, tissues, cleanup):
    """
    Build leadfield directly with command-line options.

    This is the non-interactive mode for scripting and GUI integration.
    """
    pm = ctx.obj['pm']
    project_dir = ctx.obj['project_dir']

    if not project_dir:
        echo_error("Project directory not set")
        raise click.Abort()

    tissues = list(tissues)
    echo_info(f"Tissues: {tissues}")

    total_generated = 0
    total_failed = 0

    for subject_id in subject:
        echo_info(f"\nProcessing subject: {subject_id}")

        # Verify subject exists
        m2m_dir = pm.get_m2m_dir(subject_id)
        if not m2m_dir:
            echo_error(f"Subject not found: {subject_id}")
            total_failed += len(eeg_net)
            continue

        for net in eeg_net:
            # Handle both .csv and without extension
            cap_name = net if net.endswith('.csv') else f"{net}.csv"
            net_name = net.replace('.csv', '')

            echo_info(f"  Generating leadfield for: {net_name}")

            result = build_leadfield_for_subject(
                subject_id=subject_id,
                eeg_cap=cap_name,
                tissues=tissues,
                pm=pm,
                cleanup=cleanup,
            )

            if result:
                total_generated += 1
                echo_success(f"  ✓ {net_name} completed")
            else:
                total_failed += 1
                echo_error(f"  ✗ {net_name} failed")

    # Summary
    click.echo()
    echo_header("Generation Complete")
    click.echo(f"Total generated: {total_generated}")
    click.echo(f"Total failed: {total_failed}")

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


@cli.command('list-caps')
@click.option('--subject', '-s', required=True, help='Subject ID')
@click.pass_context
def list_caps_cmd(ctx, subject):
    """List available EEG caps for a subject."""
    caps = list_available_caps(subject)

    if not caps:
        echo_warning(f"No EEG caps found for subject {subject}")
        return

    echo_header(f"EEG Caps for Subject {subject}")
    for i, cap in enumerate(caps, 1):
        net_name = cap.replace('.csv', '')
        click.echo(f"{i:3d}. {net_name}")

    echo_info(f"Total: {len(caps)} cap(s)")


@cli.command('list-leadfields')
@click.option('--subject', '-s', required=True, help='Subject ID')
@click.pass_context
def list_leadfields_cmd(ctx, subject):
    """List existing leadfields for a subject."""
    leadfields = list_existing_leadfields(subject)

    if not leadfields:
        echo_warning(f"No leadfields found for subject {subject}")
        echo_info("Use 'build' command to create leadfields")
        return

    echo_header(f"Leadfields for Subject {subject}")
    for net_name, hdf5_path, size_gb in leadfields:
        click.echo(f"  {net_name:<30} ({size_gb:.2f} GB)")
        click.echo(f"    Path: {hdf5_path}")

    echo_info(f"Total: {len(leadfields)} leadfield(s)")


# =============================================================================
# EXECUTION LOGIC
# =============================================================================

def build_leadfield_for_subject(
    subject_id: str,
    eeg_cap: str,
    tissues: List[int],
    pm,
    cleanup: bool = True,
) -> bool:
    """
    Build a leadfield for a subject.

    Args:
        subject_id: Subject ID
        eeg_cap: EEG cap filename (e.g., 'GSN-HydroCel-185.csv')
        tissues: List of tissue types
        pm: PathManager instance
        cleanup: Whether to clean up old files

    Returns:
        True if successful, False otherwise
    """
    from tit.opt.leadfield import LeadfieldGenerator

    try:
        # Get paths
        m2m_dir = pm.get_m2m_dir(subject_id)
        if not m2m_dir:
            echo_error(f"M2M directory not found for subject {subject_id}")
            return False

        eeg_positions_dir = pm.get_eeg_positions_dir(subject_id)
        if not eeg_positions_dir:
            echo_error(f"EEG positions directory not found for subject {subject_id}")
            return False

        eeg_cap_path = os.path.join(eeg_positions_dir, eeg_cap)
        if not os.path.exists(eeg_cap_path):
            echo_error(f"EEG cap file not found: {eeg_cap_path}")
            return False

        leadfield_dir = pm.get_leadfield_dir(subject_id)
        if not leadfield_dir:
            # Fallback: create leadfields directory in subject directory
            leadfield_dir = os.path.join(pm.get_subject_dir(subject_id), "leadfields")
            os.makedirs(leadfield_dir, exist_ok=True)

        net_name = eeg_cap.replace('.csv', '')

        # Create leadfield generator
        gen = LeadfieldGenerator(m2m_dir, electrode_cap=net_name)

        # Setup logger
        derivatives_dir = pm.get_derivatives_dir()
        log_dir = os.path.join(derivatives_dir, 'tit', 'logs', f'sub-{subject_id}')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f'Leadfield_{net_name}_{int(time.time())}.log')

        logger = logging_util.get_logger(
            f'LeadfieldBuilder-{subject_id}-{net_name}',
            log_file,
            overwrite=False,
            console=True
        )
        logging_util.configure_external_loggers(['simnibs', 'mesh_io'], logger)

        logger.info(f"Generating leadfield for {subject_id} with {net_name}")
        logger.info(f"Output directory: {leadfield_dir}")
        logger.info(f"Tissues: {tissues}")

        start_time = time.time()

        # Generate leadfield
        result = gen.generate_leadfield(
            output_dir=leadfield_dir,
            tissues=tissues,
            eeg_cap_path=eeg_cap_path,
            cleanup=cleanup,
        )

        elapsed = time.time() - start_time
        logger.info(f"Leadfield generation completed in {elapsed/60:.1f} minutes")
        logger.info(f"HDF5 file: {result['hdf5']}")

        return True

    except Exception as e:
        echo_error(f"Failed to generate leadfield: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    cli(obj={})
