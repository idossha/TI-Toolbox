#!/usr/bin/env simnibs_python
"""Validate a selected Flex candidate through the live API and standard SESSION.

Run serially with the existing server token in TIT_SERVER_TOKEN. All new files
are confined to --output; this deliberately does not run TI-Toolbox's complete
postprocessing pipeline, which can rewrite the subject's cached T1 MNI image.
The SESSION still uses the standard SimulationConfig and TISimulation builder,
actual electrode remeshing, FEM, and its configured cortical-surface mapping.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import resource
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--server", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    from tit.paths import get_path_manager
    from tit.config_io import deserialize_config
    from tit.sim.config import SimulationConfig
    from tit.sim.TI import TISimulation
    from simnibs.mesh_tools import mesh_io
    from simnibs.utils.TI_utils import get_maxTI

    pm = get_path_manager(args.project)
    manifest = json.loads(
        (
            Path(pm.flex_search_run(args.subject, args.run)) / "candidate_manifest.json"
        ).read_text()
    )
    candidate_id = manifest["accepted_candidate_id"]
    if not candidate_id:
        raise RuntimeError("No accepted candidate to replay")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    query = urlencode({"subject": args.subject, "kind": "flex", "run": args.run})
    token = os.environ["TIT_SERVER_TOKEN"]

    def get_api(path: str) -> dict:
        request = Request(
            args.server + path, headers={"Authorization": "Bearer " + token}
        )
        with urlopen(request, timeout=60) as response:
            if response.status != 200:
                raise RuntimeError("Candidate API did not return HTTP 200")
            return json.load(response)

    listing = get_api("/api/catalog/optimization-candidates?" + query)
    detail = get_api(
        "/api/catalog/optimization-candidates/"
        + quote(candidate_id, safe="")
        + "?"
        + query
    )
    if not any(row["id"] == candidate_id for row in listing["candidates"]):
        raise RuntimeError("Accepted candidate missing from live API listing")
    (output / "candidate_api.json").write_text(
        json.dumps(detail, indent=2, allow_nan=False) + "\n"
    )
    config = deserialize_config(SimulationConfig, detail["simulation_config"])
    montage = config.montages[0]
    simulation = TISimulation(config, montage, logging.getLogger("tit.sim.validation"))
    session = simulation._build_session(str(output / "session"))
    poses = montage.electrode_poses
    for index, position_list in enumerate(session.poslists):
        expected_A = config.intensities[index] / 1000.0
        np.testing.assert_array_equal(position_list.currents, [expected_A, -expected_A])
        for offset, electrode in enumerate(position_list.electrode):
            pose = np.asarray(poses[2 * index + offset])
            np.testing.assert_array_equal(electrode.centre, pose[:3, 3])
            np.testing.assert_array_equal(
                electrode.pos_ydir, pose[:3, 3] + 20 * pose[:3, 1]
            )
            np.testing.assert_array_equal(
                electrode.dimensions, config.electrode_dimensions
            )
            np.testing.assert_array_equal(
                electrode.thickness, [config.gel_thickness, config.rubber_thickness]
            )
    print(
        "Live candidate list/detail HTTP 200; exact SESSION centres, orientation, current and dimensions verified",
        flush=True,
    )
    started = time.perf_counter()
    files = session.run(cpus=1)
    elapsed = time.perf_counter() - started
    if len(files) != 2:
        raise RuntimeError("Expected two final carrier meshes")
    meshes = [mesh_io.read_msh(filename).crop_mesh(tags=2) for filename in files]
    np.testing.assert_array_equal(
        meshes[0].nodes.node_coord, meshes[1].nodes.node_coord
    )
    np.testing.assert_array_equal(
        meshes[0].elm.node_number_list, meshes[1].elm.node_number_list
    )
    fields = [mesh.field["E"].value for mesh in meshes]
    if not all(np.isfinite(field).all() for field in fields):
        raise RuntimeError("Nonfinite final carrier field")
    envelope = get_maxTI(fields[0], fields[1])
    roi = manifest["config"]["roi"]
    if roi.get("_type") != "SphericalROI" or roi.get("use_mni"):
        raise RuntimeError("This metric fixture requires a subject-space spherical ROI")
    center = np.array([roi[axis] for axis in ("x", "y", "z")])
    mask = (
        np.linalg.norm(meshes[0].elements_baricenters().value - center, axis=1)
        <= roi["radius"]
    )
    if not mask.any() or mask.all():
        raise RuntimeError("Final target/complement must both contain samples")
    target_mean = float(np.mean(envelope[mask]))
    background_p95 = float(np.percentile(envelope[~mask], 95))
    result = {
        "candidate_id": candidate_id,
        "api_http_status": 200,
        "scope": "standard SimulationConfig SESSION; full TI-Toolbox postprocessing not run",
        "session_seconds": elapsed,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "carrier_meshes": files,
        "finite_carrier_fields": True,
        "final_roi_samples": int(mask.sum()),
        "final_background_samples": int((~mask).sum()),
        "final_roi_mean": target_mean,
        "final_background_p95": background_p95,
        "final_target_background_ratio": target_mean / background_p95,
        "metric_weighting": "unweighted element samples",
        "optimization_estimates": detail["candidate"],
        "optimizer_termination": manifest.get("optimizer_termination"),
    }
    (output / "replay_receipt.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
