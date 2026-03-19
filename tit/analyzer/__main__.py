"""Entry point: simnibs_python -m tit.analyzer config.json"""

from __future__ import annotations

import json
import sys

from tit.paths import get_path_manager


def main() -> None:
    from tit.logger import add_stream_handler

    add_stream_handler("tit.analyzer")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    project_dir = data.pop("project_dir", None)
    if project_dir:
        get_path_manager(project_dir)

    mode = data.pop("mode", "single")
    if mode == "group":
        _run_group(data)
    else:
        _run_single(data)


def _run_group(data: dict) -> None:
    from tit.analyzer import run_group_analysis

    run_group_analysis(
        subject_ids=data["subject_ids"],
        simulation=data["simulation"],
        space=data.get("space", "mesh"),
        tissue_type=data.get("tissue_type", "GM"),
        analysis_type=data.get("analysis_type", "spherical"),
        center=tuple(data["center"]) if data.get("center") else None,
        radius=data.get("radius"),
        coordinate_space=data.get("coordinate_space", "subject"),
        atlas=data.get("atlas"),
        region=data.get("region"),
        visualize=data.get("visualize", True),
        output_dir=data.get("output_dir"),
    )


def _run_single(data: dict) -> None:
    from tit.analyzer import Analyzer
    from tit.analyzer.field_selector import list_field_targets

    analysis_type = data.pop("analysis_type")
    visualize = data.get("visualize", True)
    subject_id = data["subject_id"]
    simulation = data["simulation"]
    space = data.get("space", "mesh")
    tissue_type = data.get("tissue_type", "GM")
    base_output_dir = data.get("output_dir")
    targets = list_field_targets(subject_id, simulation, space, tissue_type)

    for target in targets:
        measure_output_dir = base_output_dir
        if base_output_dir and len(targets) > 1:
            import os

            measure_output_dir = os.path.join(base_output_dir, target.measure)
            if os.path.exists(measure_output_dir) and os.listdir(measure_output_dir):
                print(
                    f"[INFO] Skipping analysis for measure '{target.measure}' because output already exists: {measure_output_dir}"
                )
                continue

        analyzer = Analyzer(
            subject_id=subject_id,
            simulation=simulation,
            space=space,
            tissue_type=tissue_type,
            measure=target.measure if len(targets) > 1 else None,
            output_dir=measure_output_dir,
        )

        if analysis_type == "spherical":
            analyzer.analyze_sphere(
                center=tuple(data["center"]),
                radius=data["radius"],
                coordinate_space=data.get("coordinate_space", "subject"),
                visualize=visualize,
            )
        elif analysis_type == "cortical":
            analyzer.analyze_cortex(
                atlas=data["atlas"],
                region=data.get("region", ""),
                visualize=visualize,
            )


if __name__ == "__main__":
    main()
