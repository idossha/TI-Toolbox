import csv, json, os, re


class OutputAlgorithms:
    @staticmethod
    def create_csv_data(results, roi_name):
        csv_data = [
            [
                "Montage",
                "Current_Ch1_mA",
                "Current_Ch2_mA",
                "TImax_ROI",
                "TImean_ROI",
                "TImean_GM",
                "Focality",
                "Composite_Index",
                "n_elements",
            ]
        ]

        timax_values, timean_values, focality_values, composite_values = [], [], [], []

        for mesh_name, data in results.items():
            formatted_name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace(
                "_and_", " <> "
            )

            ti_max = data.get(f"{roi_name}_TImax_ROI")
            ti_mean = data.get(f"{roi_name}_TImean_ROI")
            ti_mean_gm = data.get(f"{roi_name}_TImean_GM")
            focality = data.get(f"{roi_name}_Focality")

            composite_index = (
                ti_mean * focality
                if ti_mean is not None and focality is not None
                else None
            )

            csv_data.append(
                [
                    formatted_name,
                    f"{data.get('current_ch1_mA', 0):.1f}",
                    f"{data.get('current_ch2_mA', 0):.1f}",
                    f"{ti_max:.4f}" if ti_max is not None else "",
                    f"{ti_mean:.4f}" if ti_mean is not None else "",
                    f"{ti_mean_gm:.4f}" if ti_mean_gm is not None else "",
                    f"{focality:.4f}" if focality is not None else "",
                    f"{composite_index:.4f}" if composite_index is not None else "",
                    data.get(f"{roi_name}_n_elements", 0),
                ]
            )

            if ti_max is not None:
                timax_values.append(ti_max)
            if ti_mean is not None:
                timean_values.append(ti_mean)
            if focality is not None:
                focality_values.append(focality)
            if composite_index is not None:
                composite_values.append(composite_index)

        return csv_data, timax_values, timean_values, focality_values, composite_values


class VisualizationAlgorithms:
    @staticmethod
    def create_histogram_data(timax_values, timean_values, focality_values):
        return {
            "timax": timax_values,
            "timean": timean_values,
            "focality": focality_values,
        }

    @staticmethod
    def create_scatter_data(results, roi_name):
        intensity, focality, composite = [], [], []
        for data in results.values():
            ti_mean = data.get(f"{roi_name}_TImean_ROI")
            foc = data.get(f"{roi_name}_Focality")
            if ti_mean is not None and foc is not None:
                intensity.append(ti_mean)
                focality.append(foc)
                composite.append(ti_mean * foc)
        return intensity, focality, composite


class ResultsProcessor:
    def __init__(self, results, output_dir, roi_name, logger):
        self.results, self.output_dir, self.roi_name, self.logger = (
            results,
            output_dir,
            roi_name,
            logger,
        )

    def save_json_results(self):
        json_path = os.path.join(self.output_dir, "analysis_results.json")
        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=4)
        self.logger.info(f"\nResults saved to: {json_path}")
        return json_path

    def create_csv_data(self):
        csv_data = [
            [
                "Montage",
                "Current_Ch1_mA",
                "Current_Ch2_mA",
                "TImax_ROI",
                "TImean_ROI",
                "TImean_GM",
                "Focality",
                "Composite_Index",
                "n_elements",
            ]
        ]

        timax_values, timean_values, focality_values, composite_values = [], [], [], []

        for mesh_name, data in self.results.items():
            formatted_name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace(
                "_and_", " <> "
            )

            ti_max = data.get(f"{self.roi_name}_TImax_ROI")
            ti_mean = data.get(f"{self.roi_name}_TImean_ROI")
            ti_mean_gm = data.get(f"{self.roi_name}_TImean_GM")
            focality = data.get(f"{self.roi_name}_Focality")

            composite_index = (
                ti_mean * focality
                if ti_mean is not None and focality is not None
                else None
            )

            csv_data.append(
                [
                    formatted_name,
                    f"{data.get('current_ch1_mA', 0):.1f}",
                    f"{data.get('current_ch2_mA', 0):.1f}",
                    f"{ti_max:.4f}" if ti_max is not None else "",
                    f"{ti_mean:.4f}" if ti_mean is not None else "",
                    f"{ti_mean_gm:.4f}" if ti_mean_gm is not None else "",
                    f"{focality:.4f}" if focality is not None else "",
                    f"{composite_index:.4f}" if composite_index is not None else "",
                    data.get(f"{self.roi_name}_n_elements", 0),
                ]
            )

            if ti_max is not None:
                timax_values.append(ti_max)
            if ti_mean is not None:
                timean_values.append(ti_mean)
            if focality is not None:
                focality_values.append(focality)
            if composite_index is not None:
                composite_values.append(composite_index)

        return csv_data, timax_values, timean_values, focality_values, composite_values

    def save_csv_results(self):
        csv_data, _, _, _, _ = self.create_csv_data()
        csv_path = os.path.join(self.output_dir, "final_output.csv")
        with open(csv_path, "w", newline="") as f:
            csv.writer(f).writerows(csv_data)
        self.logger.info(f"CSV output created: {csv_path}")
        return csv_path


class ResultsVisualizer:
    def __init__(self, output_dir, logger):
        self.output_dir, self.logger = output_dir, logger

    def create_histograms(self, timax_values, timean_values, focality_values):
        try:
            from tit.plotting.ti_metrics import plot_montage_distributions

            hist_path = os.path.join(self.output_dir, "montage_distributions.png")
            saved = plot_montage_distributions(
                timax_values=timax_values,
                timean_values=timean_values,
                focality_values=focality_values,
                output_file=hist_path,
                dpi=300,
            )
            if saved:
                self.logger.info(f"Histogram visualization saved: {saved}")
            return saved
        except:
            return None

    def create_scatter_plot(self, results, roi_name):
        try:
            intensity, focality, composite = [], [], []
            for data in results.values():
                ti_mean = data.get(f"{roi_name}_TImean_ROI")
                foc = data.get(f"{roi_name}_Focality")
                if ti_mean is not None and foc is not None:
                    intensity.append(ti_mean)
                    focality.append(foc)
                    composite.append(ti_mean * foc)

            if not intensity or not focality:
                return None

            from tit.plotting.ti_metrics import plot_intensity_vs_focality

            scatter_path = os.path.join(
                self.output_dir, "intensity_vs_focality_scatter.png"
            )
            saved = plot_intensity_vs_focality(
                intensity=intensity,
                focality=focality,
                composite=composite,
                output_file=scatter_path,
                dpi=300,
            )
            if saved:
                self.logger.info(f"Scatter visualization saved: {saved}")
            return saved
        except:
            return None

    def generate_visualizations(
        self, results, roi_name, timax_values, timean_values, focality_values
    ):
        saved_files = []
        if timax_values or timean_values or focality_values:
            self.logger.info("Generating visualizations...")
            hist_path = self.create_histograms(
                timax_values, timean_values, focality_values
            )
            if hist_path:
                saved_files.append(hist_path)
            scatter_path = self.create_scatter_plot(results, roi_name)
            if scatter_path:
                saved_files.append(scatter_path)
        return saved_files


class ResultsManager:
    def __init__(self, results, output_dir, roi_name, logger):
        self.results, self.output_dir, self.roi_name, self.logger = (
            results,
            output_dir,
            roi_name,
            logger,
        )
        self.processor = ResultsProcessor(results, output_dir, roi_name, logger)
        self.visualizer = ResultsVisualizer(output_dir, logger)

    def process_and_save_results(self):
        json_path = self.processor.save_json_results()
        csv_data, timax_values, timean_values, focality_values, composite_values = (
            self.processor.create_csv_data()
        )
        csv_path = self.processor.save_csv_results()
        viz_paths = self.visualizer.generate_visualizations(
            self.results, self.roi_name, timax_values, timean_values, focality_values
        )

        return {
            "json_path": json_path,
            "csv_path": csv_path,
            "visualization_paths": viz_paths,
            "summary_stats": {
                "total_montages": len(self.results),
                "timax_range": (
                    (min(timax_values), max(timax_values)) if timax_values else None
                ),
                "timean_range": (
                    (min(timean_values), max(timean_values)) if timean_values else None
                ),
                "focality_range": (
                    (min(focality_values), max(focality_values))
                    if focality_values
                    else None
                ),
                "composite_range": (
                    (min(composite_values), max(composite_values))
                    if composite_values
                    else None
                ),
            },
        }
