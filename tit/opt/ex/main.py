import os, sys, time

from tit import log as logging_util
from tit.core import get_path_manager
from tit.opt.ex.config import get_full_config
from tit.opt.ex.runner import LeadfieldProcessor, CurrentRatioGenerator, MontageGenerator, SimulationRunner
from tit.opt.ex.results import ResultsManager

def main():
    project_dir = os.getenv('PROJECT_DIR')
    subject_name = os.getenv('SUBJECT_NAME')
    if not project_dir or not subject_name:
        print("\033[0;31mError: PROJECT_DIR and SUBJECT_NAME environment variables must be set\033[0m")
        sys.exit(1)

    # Determine log file location
    log_file = os.environ.get('TI_LOG_FILE')
    if not log_file:
        # Use proper logs directory
        pm = get_path_manager()
        logs_dir = pm.get_logs_dir(subject_name)
        os.makedirs(logs_dir, exist_ok=True)
        log_file = os.path.join(logs_dir, f'ex_search_{time.strftime("%Y%m%d_%H%M%S")}.log')
    logger = logging_util.get_logger('ex_search', log_file, overwrite=False)
    logging_util.configure_external_loggers(['simnibs'], logger)

    logger.info("="*80)
    logger.info("TI Exhaustive Search - Simulation Module")
    logger.info("="*80)
    logger.info(f"Project: {project_dir}")
    logger.info(f"Subject: {subject_name}")
    logger.info("")

    try:
        config = get_full_config(logger)
        env_config, electrodes, currents, all_combinations = config['environment'], config['electrodes'], config['currents'], config['all_combinations']

        pm = get_path_manager()

        # Normalize ROI name to ensure it has exactly one .csv extension
        roi_name = env_config['ROI_NAME']
        if not roi_name.endswith('.csv'):
            roi_name += '.csv'

        output_dir = os.path.join(pm.get_ex_search_dir(subject_name), f"{roi_name}_{env_config['SELECTED_EEG_NET']}")
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Output directory: {output_dir}")

        roi_file = os.path.join(pm.get_m2m_dir(subject_name), 'ROIs', roi_name)
        leadfield_processor = LeadfieldProcessor(env_config['LEADFIELD_HDF'], roi_file, roi_name, logger)
        leadfield_processor.initialize()

        current_generator = CurrentRatioGenerator(currents['total_current'], currents['current_step'], currents['channel_limit'], logger)
        current_ratios = current_generator.generate_ratios()
        logger.info(f"Generated {len(current_ratios)} current ratio combinations")

        montage_generator = MontageGenerator(electrodes['E1_plus'], electrodes['E1_minus'], electrodes['E2_plus'], electrodes['E2_minus'], current_ratios, all_combinations, logger)
        simulator = SimulationRunner(leadfield_processor, montage_generator, output_dir, logger)
        results = simulator.run_simulation()

        results_manager = ResultsManager(results, output_dir, roi_name, logger)
        output_info = results_manager.process_and_save_results()

        logger.info("Ex-search completed successfully!")
        logger.info(f"Results: {output_info['json_path']}")
        logger.info(f"Summary: {output_info['csv_path']}")
        if output_info['visualization_paths']: logger.info(f"Visualizations: {len(output_info['visualization_paths'])} files generated")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
