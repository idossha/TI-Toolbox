import os, time, signal
from itertools import product
from simnibs.utils import TI_utils as TI

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in os.path.sys.path: os.path.sys.path.insert(0, project_root)

from core.roi import ROICoordinateHelper, find_roi_element_indices, find_grey_matter_indices, calculate_roi_metrics
from .logic import generate_current_ratios, calculate_total_combinations, generate_montage_combinations

class LeadfieldAlgorithms:
    @staticmethod
    def load_leadfield(leadfield_hdf):
        start = time.time()
        leadfield, mesh, idx_lf = TI.load_leadfield(leadfield_hdf)
        load_time = time.time() - start
        return leadfield, mesh, idx_lf, load_time

    @staticmethod
    def load_roi_coordinates(roi_file):
        if not os.path.exists(roi_file):
            raise FileNotFoundError(f"ROI file not found: {roi_file}")
        roi_coords = ROICoordinateHelper.load_roi_from_csv(roi_file)
        if roi_coords is None:
            raise ValueError("Could not load ROI coordinates")
        if hasattr(roi_coords, 'tolist'): roi_coords = roi_coords.tolist()
        return roi_coords

    @staticmethod
    def find_roi_elements(mesh, roi_coords, roi_radius=3.0):
        return find_roi_element_indices(mesh, roi_coords, radius=roi_radius)

    @staticmethod
    def find_grey_matter_elements(mesh):
        return find_grey_matter_indices(mesh, grey_matter_tags=[2])

    @staticmethod
    def calculate_roi_metrics_for_field(ti_max_full, roi_indices, roi_volumes, gm_indices, gm_volumes):
        return calculate_roi_metrics(ti_max_full[roi_indices], roi_volumes,
                                   ti_field_gm=ti_max_full[gm_indices], gm_volumes=gm_volumes)

class TIAlgorithms:
    @staticmethod
    def calculate_ti_field(leadfield, idx_lf, roi_indices, roi_volumes, gm_indices, gm_volumes, e1_plus, e1_minus, current_ch1_mA, e2_plus, e2_minus, current_ch2_mA, roi_name):
        ef1 = TI.get_field([e1_plus, e1_minus, current_ch1_mA/1000], leadfield, idx_lf)
        ef2 = TI.get_field([e2_plus, e2_minus, current_ch2_mA/1000], leadfield, idx_lf)
        ti_max_full = TI.get_maxTI(ef1, ef2)

        roi_metrics = LeadfieldAlgorithms.calculate_roi_metrics_for_field(ti_max_full, roi_indices, roi_volumes, gm_indices, gm_volumes)

        return {
            f'{roi_name}_TImax_ROI': roi_metrics['TImax_ROI'],
            f'{roi_name}_TImean_ROI': roi_metrics['TImean_ROI'],
            f'{roi_name}_TImean_GM': roi_metrics.get('TImean_GM', 0.0),
            f'{roi_name}_Focality': roi_metrics.get('Focality', 0.0),
            f'{roi_name}_n_elements': roi_metrics['n_elements'],
            'current_ch1_mA': current_ch1_mA,
            'current_ch2_mA': current_ch2_mA
        }

class StopFlag:
    def __init__(self): self.value = False
    def set(self): self.value = True

class LeadfieldProcessor:
    def __init__(self, leadfield_hdf, roi_file, roi_name, logger):
        self.leadfield_hdf, self.roi_file, self.roi_name, self.logger = leadfield_hdf, roi_file, roi_name, logger
        self.leadfield = self.mesh = self.idx_lf = None
        self.roi_coords = self.roi_indices = self.roi_volumes = None
        self.gm_indices = self.gm_volumes = None

    def load_leadfield(self):
        self.logger.info(f"Loading leadfield: {self.leadfield_hdf}")
        self.leadfield, self.mesh, self.idx_lf, load_time = LeadfieldAlgorithms.load_leadfield(self.leadfield_hdf)
        self.logger.info(f"Loaded in {load_time:.1f}s")

    def load_roi_coordinates(self):
        self.roi_coords = LeadfieldAlgorithms.load_roi_coordinates(self.roi_file)
        self.logger.info(f"ROI coords: {self.roi_coords}")

    def find_roi_elements(self, roi_radius=3.0):
        self.logger.info(f"Finding ROI elements (radius={roi_radius}mm)...")
        self.roi_indices, self.roi_volumes = LeadfieldAlgorithms.find_roi_elements(self.mesh, self.roi_coords, roi_radius)
        self.logger.info(f"Found {len(self.roi_indices)} ROI elements")

    def find_grey_matter_elements(self):
        self.logger.info("Finding grey matter elements...")
        self.gm_indices, self.gm_volumes = LeadfieldAlgorithms.find_grey_matter_elements(self.mesh)
        self.logger.info(f"Found {len(self.gm_indices)} GM elements")

    def calculate_roi_metrics_for_field(self, ti_max_full):
        return LeadfieldAlgorithms.calculate_roi_metrics_for_field(ti_max_full, self.roi_indices, self.roi_volumes, self.gm_indices, self.gm_volumes)

    def initialize(self):
        self.load_leadfield()
        self.load_roi_coordinates()
        self.find_roi_elements()
        self.find_grey_matter_elements()

class CurrentRatioGenerator:
    def __init__(self, total_current, current_step, channel_limit, logger):
        self.total_current, self.current_step, self.channel_limit, self.logger = total_current, current_step, channel_limit or (total_current / 2.0), logger

    def generate_ratios(self):
        ratios, exceeded = generate_current_ratios(self.total_current, self.current_step, self.channel_limit)
        if exceeded:
            self.logger.warning("Channel limit exceeds total current")
        return ratios

class MontageGenerator:
    def __init__(self, e1_plus, e1_minus, e2_plus, e2_minus, current_ratios, all_combinations, logger):
        self.e1_plus, self.e1_minus, self.e2_plus, self.e2_minus = e1_plus, e1_minus, e2_plus, e2_minus
        self.current_ratios, self.all_combinations, self.logger = current_ratios, all_combinations, logger

    def get_total_combinations(self):
        return calculate_total_combinations(self.e1_plus, self.e1_minus, self.e2_plus, self.e2_minus, self.current_ratios, self.all_combinations)

    def generate_montages(self):
        return generate_montage_combinations(self.e1_plus, self.e1_minus, self.e2_plus, self.e2_minus, self.current_ratios, self.all_combinations)

    def log_configuration_summary(self):
        total = self.get_total_combinations()
        self.logger.info(f"\n{'='*80}")
        self.logger.info("Starting TI Calculations" + (" (All Combinations)" if self.all_combinations else " (Bucketed)"))
        self.logger.info(f"{'='*80}")
        self.logger.info(f"Total combinations: {total}")
        if self.all_combinations:
            valid = [(e1p, e1m, e2p, e2m) for e1p, e1m, e2p, e2m in product(self.e1_plus, repeat=4)
                    if len(set([e1p, e1m, e2p, e2m])) == 4]
            self.logger.info(f"Electrodes: {len(self.e1_plus)} | Valid combinations: {len(valid)}")
        else:
            self.logger.info(f"E1+/-: {len(self.e1_plus)}/{len(self.e1_minus)} | E2+/-: {len(self.e2_plus)}/{len(self.e2_minus)}")
        self.logger.info(f"Current ratios: {len(self.current_ratios)}\n{'='*80}\n")

class TISimulator:
    def __init__(self, leadfield_processor, logger):
        self.leadfield_processor, self.logger = leadfield_processor, logger

    def calculate_ti_field(self, e1_plus, e1_minus, current_ch1_mA, e2_plus, e2_minus, current_ch2_mA):
        return TIAlgorithms.calculate_ti_field(
            self.leadfield_processor.leadfield, self.leadfield_processor.idx_lf,
            self.leadfield_processor.roi_indices, self.leadfield_processor.roi_volumes,
            self.leadfield_processor.gm_indices, self.leadfield_processor.gm_volumes,
            e1_plus, e1_minus, current_ch1_mA, e2_plus, e2_minus, current_ch2_mA,
            self.leadfield_processor.roi_name
        )

class SimulationRunner:
    def __init__(self, leadfield_processor, montage_generator, output_dir, logger):
        self.leadfield_processor, self.montage_generator, self.output_dir, self.logger = leadfield_processor, montage_generator, output_dir, logger
        self.ti_simulator = TISimulator(leadfield_processor, logger)

    def setup_signal_handler(self):
        stop_flag = StopFlag()
        signal.signal(signal.SIGINT, lambda s, f: stop_flag.set())
        signal.signal(signal.SIGTERM, lambda s, f: stop_flag.set())
        return stop_flag

    def create_montage_name(self, e1_plus, e1_minus, e2_plus, e2_minus, current_ch1_mA, current_ch2_mA):
        return f"{e1_plus}_{e1_minus}_and_{e2_plus}_{e2_minus}_I1-{current_ch1_mA:.1f}mA_I2-{current_ch2_mA:.1f}mA"

    def run_simulation(self):
        stop_flag = self.setup_signal_handler()
        all_results, start_time = {}, time.time()
        self.montage_generator.log_configuration_summary()
        total_combinations = self.montage_generator.get_total_combinations()

        for processed, (e1_plus, e1_minus, e2_plus, e2_minus, (current_ch1_mA, current_ch2_mA)) in enumerate(self.montage_generator.generate_montages(), 1):
            if stop_flag.value:
                self.logger.warning("Interrupted")
                break

            montage_name = self.create_montage_name(e1_plus, e1_minus, e2_plus, e2_minus, current_ch1_mA, current_ch2_mA)
            mesh_key = f"TI_field_{montage_name}.msh"

            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total_combinations - processed) / rate if rate > 0 else 0

            self.logger.info(f"[{processed}/{total_combinations}] {montage_name}")
            self.logger.info(f"  Progress: {100*processed/total_combinations:.1f}% | Rate: {rate:.2f} montages/sec | ETA: {eta/60:.1f} min")

            try:
                sim_start = time.time()
                result_data = self.ti_simulator.calculate_ti_field(e1_plus, e1_minus, current_ch1_mA, e2_plus, e2_minus, current_ch2_mA)
                all_results[mesh_key] = result_data

                roi_name = self.leadfield_processor.roi_name
                self.logger.info(f"  Completed in {time.time()-sim_start:.2f}s | I1={current_ch1_mA:.1f}mA, I2={current_ch2_mA:.1f}mA | "
                               f"TImax={result_data[f'{roi_name}_TImax_ROI']:.4f} V/m, "
                               f"TImean={result_data[f'{roi_name}_TImean_ROI']:.4f} V/m, "
                               f"Focality={result_data[f'{roi_name}_Focality']:.4f}")
            except Exception as e:
                self.logger.error(f"  Error: {montage_name}: {e}")

        total_time = time.time() - start_time
        self.logger.info(f"\n{'='*80}")
        self.logger.info("Calculation Summary")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"Processed: {processed}/{total_combinations} montages")
        self.logger.info(f"Total time: {total_time/60:.1f} minutes ({total_time/processed:.2f}s per montage)")
        self.logger.info(f"Output: {self.output_dir}")
        self.logger.info(f"{'='*80}")

        return all_results
