"""Entry point: simnibs_python -m tit.analyzer config.json"""


import json
import sys

from tit.paths import get_path_manager


def main() -> None:
    from tit.logger import add_stream_handler, setup_logging

    setup_logging("INFO")
    add_stream_handler("tit.analyzer")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    project_dir = data.pop("project_dir", None)
    if project_dir:
        get_path_manager(project_dir)

    mode = data.pop("mode", "single")
    print(f"Starting {mode} analysis...", flush=True)

    if mode == "group":
        _run_group(data)
    else:
        _run_single(data)

    print("✓ Analysis complete.", flush=True)


def _run_group(data: dict) -> None:
    from tit.analyzer import run_group_analysis

    print(
        f"Group analysis: {len(data['subject_ids'])} subjects, "
        f"space={data.get('space', 'mesh')}, "
        f"type={data.get('analysis_type', 'spherical')}",
        flush=True,
    )

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
        region=data.get("regions") or data.get("region"),
        visualize=data.get("visualize", True),
        output_dir=data.get("output_dir"),
    )


def _run_single(data: dict) -> None:
    from tit.analyzer import Analyzer

    analysis_type = data.pop("analysis_type")
    visualize = data.get("visualize", True)

    print(
        f"Single analysis: subject={data['subject_id']}, "
        f"sim={data['simulation']}, space={data.get('space', 'mesh')}, "
        f"type={analysis_type}",
        flush=True,
    )

    analyzer = Analyzer(
        subject_id=data["subject_id"],
        simulation=data["simulation"],
        space=data.get("space", "mesh"),
        tissue_type=data.get("tissue_type", "GM"),
        output_dir=data.get("output_dir"),
    )

    if analysis_type == "spherical":
        analyzer.analyze_sphere(
            center=tuple(data["center"]),
            radius=data["radius"],
            coordinate_space=data.get("coordinate_space", "subject"),
            visualize=visualize,
        )
    elif analysis_type == "cortical":
        region = data.get("regions") or data.get("region", "")
        analyzer.analyze_cortex(
            atlas=data["atlas"],
            region=region,
            visualize=visualize,
        )


if __name__ == "__main__":
    main()
