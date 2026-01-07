#!/usr/bin/env simnibs_python
"""
Permutation Analysis CLI (cluster-based permutation testing).

Docker-first:
- Interactive default (no args)
- Direct mode via flags
"""

from __future__ import annotations

from typing import Any, Dict
from pathlib import Path

from tit.cli.base import ArgumentDefinition, BaseCLI, InteractivePrompt
from tit.cli import utils
from tit.stats import permutation_analysis
from tit.core import get_path_manager


class PermutationCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__("Unified cluster-based permutation testing.")
        self.add_argument(ArgumentDefinition(name="csv", type=str, help="Path to CSV file", required=True))
        self.add_argument(ArgumentDefinition(name="name", type=str, help="Analysis name", required=True))
        self.add_argument(ArgumentDefinition(name="analysis_type", type=str, choices=["group_comparison", "correlation"], help="group_comparison|correlation", required=True))
        self.add_argument(ArgumentDefinition(name="cluster_threshold", type=float, help="Cluster threshold p", default=0.05))
        self.add_argument(ArgumentDefinition(name="cluster_stat", type=str, choices=["mass", "size"], default="mass", help="mass|size"))
        self.add_argument(ArgumentDefinition(name="n_permutations", type=int, help="Number of permutations", default=1000))
        self.add_argument(ArgumentDefinition(name="alpha", type=float, help="Cluster-level alpha", default=0.05))
        self.add_argument(ArgumentDefinition(name="n_jobs", type=int, help="Parallel jobs (-1=all)", default=-1))
        self.add_argument(ArgumentDefinition(name="use_weights", type=bool, help="Use weights (correlation only)", default=False))
        self.add_argument(ArgumentDefinition(name="tissue_type", type=str, choices=["grey", "white", "all"], default="grey", help="grey|white|all"))
        self.add_argument(ArgumentDefinition(name="nifti_pattern", type=str, help="Custom nifti pattern", required=False))
        self.add_argument(ArgumentDefinition(name="quiet", type=bool, help="Quiet", default=False))
        self.add_argument(ArgumentDefinition(name="save_perm_log", type=bool, help="Save permutation log", default=False))

    def run_interactive(self) -> int:
        utils.echo_header("Permutation Analysis (interactive)")
        pm = get_path_manager()
        csv_candidates: list[str] = []
        if pm.project_dir:
            proj = Path(pm.project_dir)
            # Only accept CSV files from projectID/derivatives/ti-toolbox/stats/data/*.csv
            stats_data_dir = proj / "derivatives" / "ti-toolbox" / "stats" / "data"
            if stats_data_dir.is_dir():
                csv_candidates += [str(p) for p in sorted(stats_data_dir.glob("*.csv"))]
        csv_path = utils.choose_or_enter(prompt="CSV path", options=csv_candidates, help_text="Select a CSV file or choose 'Enter manually…'")
        name = utils.ask_required("Analysis name", default=f"perm_{utils.now_compact()}")
        analysis_type = self._prompt_for_value(
            InteractivePrompt(name="analysis_type", prompt_text="Analysis type", choices=["group_comparison", "correlation"], default="group_comparison")
        )
        if not utils.review_and_confirm(
            "Review (permutation analysis)",
            items=[("CSV", csv_path), ("Analysis name", name), ("Analysis type", analysis_type)],
            default_yes=True,
        ):
            utils.echo_warning("Cancelled.")
            return 0
        return self.execute({"csv": csv_path, "name": name, "analysis_type": analysis_type})

    def execute(self, args: Dict[str, Any]) -> int:
        config = {
            "analysis_type": str(args["analysis_type"]),
            "cluster_threshold": float(args.get("cluster_threshold", 0.05)),
            "cluster_stat": str(args.get("cluster_stat", "mass")),
            "n_permutations": int(args.get("n_permutations", 1000)),
            "alpha": float(args.get("alpha", 0.05)),
            "n_jobs": int(args.get("n_jobs", -1)),
            "use_weights": bool(args.get("use_weights", False)),
            "tissue_type": str(args.get("tissue_type", "grey")),
            "nifti_pattern": args.get("nifti_pattern"),
            "quiet": bool(args.get("quiet", False)),
            "save_perm_log": bool(args.get("save_perm_log", False)),
        }
        permutation_analysis.run_analysis(
            subject_configs=str(args["csv"]),
            analysis_name=str(args["name"]),
            config=config,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(PermutationCLI().run())
