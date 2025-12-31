import csv, json, os, re

class OutputAlgorithms:
    @staticmethod
    def create_csv_data(results, roi_name):
        csv_data = [['Montage', 'Current_Ch1_mA', 'Current_Ch2_mA',
                     'TImax_ROI', 'TImean_ROI', 'TImean_GM',
                     'Focality', 'Composite_Index', 'n_elements']]

        timax_values, timean_values, focality_values, composite_values = [], [], [], []

        for mesh_name, data in results.items():
            formatted_name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")

            ti_max = data.get(f'{roi_name}_TImax_ROI')
            ti_mean = data.get(f'{roi_name}_TImean_ROI')
            ti_mean_gm = data.get(f'{roi_name}_TImean_GM')
            focality = data.get(f'{roi_name}_Focality')

            composite_index = ti_mean * focality if ti_mean is not None and focality is not None else None

            csv_data.append([
                formatted_name,
                f"{data.get('current_ch1_mA', 0):.1f}",
                f"{data.get('current_ch2_mA', 0):.1f}",
                f"{ti_max:.4f}" if ti_max is not None else '',
                f"{ti_mean:.4f}" if ti_mean is not None else '',
                f"{ti_mean_gm:.4f}" if ti_mean_gm is not None else '',
                f"{focality:.4f}" if focality is not None else '',
                f"{composite_index:.4f}" if composite_index is not None else '',
                data.get(f'{roi_name}_n_elements', 0)
            ])

            if ti_max is not None: timax_values.append(ti_max)
            if ti_mean is not None: timean_values.append(ti_mean)
            if focality is not None: focality_values.append(focality)
            if composite_index is not None: composite_values.append(composite_index)

        return csv_data, timax_values, timean_values, focality_values, composite_values

class VisualizationAlgorithms:
    @staticmethod
    def create_histogram_data(timax_values, timean_values, focality_values):
        return {
            'timax': timax_values,
            'timean': timean_values,
            'focality': focality_values
        }

    @staticmethod
    def create_scatter_data(results, roi_name):
        intensity, focality, composite = [], [], []
        for data in results.values():
            ti_mean = data.get(f'{roi_name}_TImean_ROI')
            foc = data.get(f'{roi_name}_Focality')
            if ti_mean is not None and foc is not None:
                intensity.append(ti_mean)
                focality.append(foc)
                composite.append(ti_mean * foc)
        return intensity, focality, composite

class ResultsProcessor:
    def __init__(self, results, output_dir, roi_name, logger):
        self.results, self.output_dir, self.roi_name, self.logger = results, output_dir, roi_name, logger

    def save_json_results(self):
        json_path = os.path.join(self.output_dir, 'analysis_results.json')
        with open(json_path, 'w') as f: json.dump(self.results, f, indent=4)
        self.logger.info(f"\nResults saved to: {json_path}")
        return json_path

    def create_csv_data(self):
        csv_data = [['Montage', 'Current_Ch1_mA', 'Current_Ch2_mA',
                     'TImax_ROI', 'TImean_ROI', 'TImean_GM',
                     'Focality', 'Composite_Index', 'n_elements']]

        timax_values, timean_values, focality_values, composite_values = [], [], [], []

        for mesh_name, data in self.results.items():
            formatted_name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")

            ti_max = data.get(f'{self.roi_name}_TImax_ROI')
            ti_mean = data.get(f'{self.roi_name}_TImean_ROI')
            ti_mean_gm = data.get(f'{self.roi_name}_TImean_GM')
            focality = data.get(f'{self.roi_name}_Focality')

            composite_index = ti_mean * focality if ti_mean is not None and focality is not None else None

            csv_data.append([
                formatted_name,
                f"{data.get('current_ch1_mA', 0):.1f}",
                f"{data.get('current_ch2_mA', 0):.1f}",
                f"{ti_max:.4f}" if ti_max is not None else '',
                f"{ti_mean:.4f}" if ti_mean is not None else '',
                f"{ti_mean_gm:.4f}" if ti_mean_gm is not None else '',
                f"{focality:.4f}" if focality is not None else '',
                f"{composite_index:.4f}" if composite_index is not None else '',
                data.get(f'{self.roi_name}_n_elements', 0)
            ])

            if ti_max is not None: timax_values.append(ti_max)
            if ti_mean is not None: timean_values.append(ti_mean)
            if focality is not None: focality_values.append(focality)
            if composite_index is not None: composite_values.append(composite_index)

        return csv_data, timax_values, timean_values, focality_values, composite_values

    def save_csv_results(self):
        csv_data, _, _, _, _ = self.create_csv_data()
        csv_path = os.path.join(self.output_dir, 'final_output.csv')
        with open(csv_path, 'w', newline='') as f: csv.writer(f).writerows(csv_data)
        self.logger.info(f"CSV output created: {csv_path}")
        return csv_path

class ResultsVisualizer:
    def __init__(self, output_dir, logger):
        self.output_dir, self.logger = output_dir, logger

    def create_histograms(self, timax_values, timean_values, focality_values):
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(15, 4))
            configs = [
                (timax_values, axes[0], 'TImax (V/m)', 'TImax Distribution', '#2196F3'),
                (timean_values, axes[1], 'TImean (V/m)', 'TImean Distribution', '#4CAF50'),
                (focality_values, axes[2], 'Focality', 'Focality Distribution', '#FF9800')
            ]

            for values, ax, xlabel, title, color in configs:
                if values:
                    ax.hist(values, bins=20, color=color, edgecolor='black', alpha=0.7)
                    ax.set_xlabel(xlabel, fontsize=12)
                    ax.set_ylabel('Frequency', fontsize=12)
                    ax.set_title(title, fontsize=14, fontweight='bold')
                    ax.grid(axis='y', alpha=0.3)

            plt.tight_layout()
            hist_path = os.path.join(self.output_dir, 'montage_distributions.png')
            plt.savefig(hist_path, dpi=300, bbox_inches='tight')
            plt.close()
            self.logger.info(f"Histogram visualization saved: {hist_path}")
            return hist_path
        except: return None

    def create_scatter_plot(self, results, roi_name):
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            intensity, focality, composite = [], [], []
            for data in results.values():
                ti_mean = data.get(f'{roi_name}_TImean_ROI')
                foc = data.get(f'{roi_name}_Focality')
                if ti_mean is not None and foc is not None:
                    intensity.append(ti_mean)
                    focality.append(foc)
                    composite.append(ti_mean * foc)

            if not intensity or not focality: return None

            fig, ax = plt.subplots(figsize=(6, 5))
            if any(c is not None for c in composite):
                sc = ax.scatter(intensity, focality, c=composite, cmap='viridis', s=40, edgecolor='black', alpha=0.7)
                plt.colorbar(sc, ax=ax).set_label('Composite Index', fontsize=12)
            else:
                ax.scatter(intensity, focality, s=40, edgecolor='black', alpha=0.7)

            ax.set_xlabel('TImean_ROI (V/m)', fontsize=12)
            ax.set_ylabel('Focality', fontsize=12)
            ax.set_title('Intensity vs Focality', fontsize=14, fontweight='bold')
            ax.grid(alpha=0.3)

            scatter_path = os.path.join(self.output_dir, 'intensity_vs_focality_scatter.png')
            plt.tight_layout()
            plt.savefig(scatter_path, dpi=300, bbox_inches='tight')
            plt.close()
            self.logger.info(f"Scatter visualization saved: {scatter_path}")
            return scatter_path
        except: return None

    def generate_visualizations(self, results, roi_name, timax_values, timean_values, focality_values):
        saved_files = []
        if timax_values or timean_values or focality_values:
            self.logger.info("Generating visualizations...")
            hist_path = self.create_histograms(timax_values, timean_values, focality_values)
            if hist_path: saved_files.append(hist_path)
            scatter_path = self.create_scatter_plot(results, roi_name)
            if scatter_path: saved_files.append(scatter_path)
        return saved_files

class ResultsManager:
    def __init__(self, results, output_dir, roi_name, logger):
        self.results, self.output_dir, self.roi_name, self.logger = results, output_dir, roi_name, logger
        self.processor = ResultsProcessor(results, output_dir, roi_name, logger)
        self.visualizer = ResultsVisualizer(output_dir, logger)

    def process_and_save_results(self):
        json_path = self.processor.save_json_results()
        csv_data, timax_values, timean_values, focality_values, composite_values = self.processor.create_csv_data()
        csv_path = self.processor.save_csv_results()
        viz_paths = self.visualizer.generate_visualizations(self.results, self.roi_name, timax_values, timean_values, focality_values)

        return {
            'json_path': json_path,
            'csv_path': csv_path,
            'visualization_paths': viz_paths,
            'summary_stats': {
                'total_montages': len(self.results),
                'timax_range': (min(timax_values), max(timax_values)) if timax_values else None,
                'timean_range': (min(timean_values), max(timean_values)) if timean_values else None,
                'focality_range': (min(focality_values), max(focality_values)) if focality_values else None,
                'composite_range': (min(composite_values), max(composite_values)) if composite_values else None
            }
        }
