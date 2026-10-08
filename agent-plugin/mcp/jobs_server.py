#!/usr/bin/env python3
"""TI-Toolbox job driver: an MCP server that runs pipelines through the running app.

The read-only knowledge server (``server.py``) explains the toolbox; this one *drives* it.
Every job goes through the ``tit.server`` job API of the TI-Toolbox stack the user already has
open, so it shows up live in the desktop app (job list, terminal) and writes exactly the
records, outputs and reports a job started from the app writes. Jobs are tagged
``created_by: "agent"``.

It never sees or stores the user's AI-subscription credentials: it is a local stdio process the
user's own agent (Claude Code, Codex, ...) launches. The only secret it handles is the local
server token, read from the running container (as ``tit launch`` does) and never returned.

Discovery
---------
1. ``TIT_SERVER_URL`` + ``TIT_SERVER_TOKEN`` when both are set (a native runtime, tests);
2. otherwise the running container labelled ``tit.stack=ti-toolbox-v3`` (``docker inspect``:
   ``TIT_SERVER_TOKEN``/``TIT_SERVER_PORT`` from its environment, the host project directory
   from its ``tit.host_project_dir`` label). With several projects open, ``connect`` takes the
   project path to pick one.

Zero third-party dependencies, Python 3.9+, JSON-RPC 2.0 over newline-delimited stdio.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SERVER_NAME = "ti-toolbox-jobs"
SERVER_VERSION = "0.4.0"
PROTOCOL_VERSION = "2025-06-18"

STACK_ID = "ti-toolbox-v3"  # tit/launch.py STACK_ID, desktop/src/shared/compose.ts
LABEL_STACK = "tit.stack"
LABEL_SERVICE = "tit.service"
LABEL_HOST_DIR = "tit.host_project_dir"
DEFAULT_PORT = "8765"
CREATED_BY = "agent"
TERMINAL_STATES = ("succeeded", "failed", "cancelled", "skipped", "lost")
GROUP_KINDS = ("pre", "sim", "flex", "flex_adaptive", "flex_pareto", "ex", "mex")
FLEX_KINDS = ("flex", "flex_adaptive", "flex_pareto")
SUBJECT_ID_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
)  # tit.paths.SUBJECT_ID_RE
MODALITIES = {
    "t1w": "T1w",
    "t2w": "T2w",
    "ct": "ct",
    "dwi": "dwi",
}  # tit.pre.dicom2nifti
NIFTI_SUFFIXES = (".nii.gz", ".nii")
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
SIDECAR_SUFFIXES = (".json", ".bval", ".bvec")
SCHEMA_CLASS = {
    "pre": "PreprocessConfig",
    "sim": "SimulationConfig",
    "flex": "FlexConfig",
    "flex_adaptive": "FlexConfig",
    "flex_pareto": "FlexConfig",
    "ex": "ExConfig",
    "mex": "MExConfig",
    "leadfield": "LeadfieldConfig",
    "analyzer": "AnalyzerConfig",
}

# What the desktop app sends when the user leaves a control alone, so an agent job that omits a
# field runs with the app's value, not the dataclass default.
# ponytail: hand-mirrored from desktop/src/renderer/pages/preprocess/config.ts defaultConfig,
# pages/simulator/types.ts DEFAULT_JOB_SETTINGS and pages/optimizer/flexConfig.ts
# defaultFlexFormState/buildFlexConfig; move server-side if they start drifting.
PRE_UI_DEFAULTS: Dict[str, Any] = {
    "convert_dicom": True,
    "run_fastsurfer": True,
    "run_freesurfer": False,
    "freesurfer_recon_all": True,
    "freesurfer_subregions": ["thalamus", "hippo-amygdala"],
    "freesurfer_threads": None,
    "charm_options": None,
    "charm_threads": None,
    "fastsurfer_threads": None,
    "create_m2m": True,
    "run_tissue_analysis": False,
    "run_qsiprep": False,
    "run_qsirecon": False,
    "qsiprep_config": None,
    "qsi_recon_config": None,
    "extract_dti": False,
    "skip_existing_outputs": True,
    "replace_existing_outputs": False,
}
SIM_UI_DEFAULTS: Dict[str, Any] = {
    "conductivity": "scalar",
    "aniso_maxratio": 10,
    "aniso_maxcond": 2,
    "intensities": [1.0, 1.0],
    "electrode_shape": "ellipse",
    "electrode_dimensions": [8, 8],
    "gel_thickness": 4,
    "output_fields": ["TI_max"],
    "map_to_mni": False,
    "map_to_fsavg": False,
}
FLEX_UI_DEFAULTS: Dict[str, Any] = {
    "goal": "mean",
    "postproc": "max_TI",
    "anisotropy_type": "scalar",
    "aniso_maxratio": 10.0,
    "aniso_maxcond": 2.0,
    "current_mA": 1.0,
    "electrode": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4},
    "non_roi_method": None,
    "non_roi": None,
    "thresholds": None,
    "intensity_weight": 0.0,
    "optimize_current_ratio": False,
    "ratio_total_mA": None,
    "ratio_levels": 21,
    "eeg_net": None,
    "enable_mapping": False,
    "disable_mapping_simulation": False,
    "output_folder": None,
    "run_final_electrode_simulation": False,
    "n_multistart": 1,
    "max_iterations": 500,
    "population_size": 13,
    "tolerance": 0.1,
    "mutation": "0.01,0.5",
    "recombination": 0.7,
    "min_electrode_distance": 5.0,
    "detailed_results": False,
    "visualize_valid_skin_region": True,
    "skin_visualization_net": None,
    "skin_region_margin_mm": 0.0,
    "avoid_landmark_regions": True,
}

NO_STACK = (
    "No running TI-Toolbox found. Open the TI-Toolbox desktop app on your project (or run "
    "`tit launch`), then call connect again. For a native runtime set TIT_SERVER_URL and "
    "TIT_SERVER_TOKEN."
)


class ToolError(Exception):
    """A tool failure reported to the agent as ``isError: true`` text."""


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------

_CONN: Optional[Dict[str, Any]] = None


def _docker_json(*args: str) -> Any:
    if shutil.which("docker") is None:
        raise ToolError(NO_STACK + " (docker was not found on PATH)")
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=30, check=False
    )
    if result.returncode != 0:
        raise ToolError(
            "Docker is not answering (is Docker Desktop running?): "
            + (result.stderr or result.stdout).strip()
        )
    return result.stdout


def _discover(project: Optional[str] = None) -> Dict[str, Any]:
    url, token = os.environ.get("TIT_SERVER_URL"), os.environ.get("TIT_SERVER_TOKEN")
    if url and token:
        return {"origin": url.rstrip("/"), "token": token, "host_project": None}
    ids = _docker_json(
        "ps", "--filter", f"label={LABEL_STACK}={STACK_ID}", "--format", "{{.ID}}"
    ).split()
    if not ids:
        raise ToolError(NO_STACK)
    stacks = []
    for info in json.loads(_docker_json("inspect", *ids)):
        config = info.get("Config") or {}
        labels = config.get("Labels") or {}
        if labels.get(LABEL_SERVICE) not in (None, "", "tit"):
            continue
        env = dict(p.split("=", 1) for p in config.get("Env") or [] if "=" in p)
        if not env.get("TIT_SERVER_TOKEN"):
            continue
        stacks.append(
            {
                "origin": f"http://127.0.0.1:{env.get('TIT_SERVER_PORT', DEFAULT_PORT)}",
                "token": env["TIT_SERVER_TOKEN"],
                "host_project": labels.get(LABEL_HOST_DIR),
            }
        )
    if project:
        want = os.path.realpath(os.path.expanduser(project))
        stacks = [
            s
            for s in stacks
            if s["host_project"] and os.path.realpath(s["host_project"]) == want
        ]
        if not stacks:
            raise ToolError(f"No running TI-Toolbox has {project} open. " + NO_STACK)
    if not stacks:
        raise ToolError(NO_STACK)
    if len(stacks) > 1:
        open_projects = ", ".join(str(s["host_project"]) for s in stacks)
        raise ToolError(
            f"Several TI-Toolbox projects are open ({open_projects}). Call connect with "
            "project=<one of these paths>."
        )
    return stacks[0]


def _conn() -> Dict[str, Any]:
    global _CONN
    if _CONN is None:
        _CONN = _discover()
    return _CONN


def _api(
    method: str,
    path: str,
    body: Any = None,
    *,
    timeout: float = 60.0,
    text: bool = False,
) -> Any:
    conn = _conn()
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(conn["origin"] + path, data=data, method=method)
    request.add_header("Authorization", f"Bearer {conn['token']}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.dumps(json.loads(detail), ensure_ascii=False)
        except ValueError:
            pass
        raise ToolError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ToolError(
            f"TI-Toolbox at {conn['origin']} is unreachable ({exc}). " + NO_STACK
        ) from exc
    if text:
        return raw.decode("utf-8", errors="replace")
    return json.loads(raw) if raw else None


def _q(**params: Any) -> str:
    return "?" + urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}
    )


def _subject_id(value: Any) -> str:
    if not isinstance(value, str) or not SUBJECT_ID_RE.match(value):
        raise ToolError(
            f"invalid subject id {value!r}: letters, digits, '_' and '-' only, starting with "
            "a letter or digit, without the 'sub-' prefix"
        )
    return value


def _subject_ids(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise ToolError("subject_ids must be a non-empty list of subject ids")
    return [_subject_id(v) for v in value]


def _job_summary(status: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "id",
        "kind",
        "state",
        "subject_ids",
        "group_id",
        "progress",
        "waiting_on",
        "error",
    )
    return {k: status.get(k) for k in keys if status.get(k) not in (None, [])}


# --------------------------------------------------------------------------
# connect
# --------------------------------------------------------------------------


def tool_connect(args: Dict[str, Any]) -> Dict[str, Any]:
    global _CONN
    _CONN = _discover(args.get("project"))
    project = _api("GET", "/api/project")
    if not _CONN.get("host_project"):
        _CONN["host_project"] = project.get("host_path")
    subjects = _api("GET", "/api/catalog/subjects").get("subjects", [])
    jobs = _api("GET", "/api/jobs" + _q(limit=200)) or []
    # An app older than proposals has no such setting and no approval step.
    direct = (_api("GET", "/api/settings") or {}).get("agent_auto_submit", True) is True
    return {
        "server": _CONN["origin"],
        "project": {
            "host_path": _CONN["host_project"],
            "container_path": project.get("container_path"),
            "name": project.get("name"),
        },
        "subjects": subjects,
        "active_jobs": [
            _job_summary(j) for j in jobs if j.get("state") not in TERMINAL_STATES
        ],
        "approval_required": not direct,
        "next": (
            "Plan with plan_job before submit_job; jobs appear live in the desktop app."
            if direct
            else "The user approves agent jobs in the app: plan, then propose_pipeline and "
            "wait_for_approval. submit_job / simulate_flex_result are refused."
        ),
    }


# --------------------------------------------------------------------------
# Raw data: inspect + stage (host-side; the server cannot see outside the project)
# --------------------------------------------------------------------------

_DICOM_TAGS = {
    "SeriesDescription": b"\x08\x00\x3e\x10",
    "ProtocolName": b"\x18\x00\x30\x10",
    "Modality": b"\x08\x00\x60\x00",
}


def _dicom_fields(path: Path) -> Optional[Dict[str, str]]:
    """A few header strings of a Part-10 DICOM file, or ``None`` when it is not one.

    ponytail: byte search for the tag in the first 64 KiB instead of a real element walk; a
    stray match inside an earlier value is possible but rare, and the guess is only a proposal
    the user confirms. Files without the 128-byte preamble are not recognised.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(65536)
    except OSError:
        return None
    if head[128:132] != b"DICM":
        return None
    out: Dict[str, str] = {}
    for name, tag in _DICOM_TAGS.items():
        i = head.find(tag, 132)
        if i < 0:
            continue
        j = i + 4
        vr = head[j : j + 2]
        if len(vr) == 2 and vr.isalpha() and vr.isupper():  # explicit VR: 2-byte length
            n, j = int.from_bytes(head[j + 2 : j + 4], "little"), j + 4
        else:  # implicit VR: 4-byte length
            n, j = int.from_bytes(head[j : j + 4], "little"), j + 4
        if 0 < n <= 256:
            out[name] = head[j : j + n].decode("latin-1").strip(" \x00")
    return out


def _guess_modality(text: str, dicom_modality: str = "") -> Tuple[Optional[str], str]:
    t = text.lower()
    if dicom_modality.upper() == "CT" or re.search(r"(^|[^a-z])ct([^a-z]|$)", t):
        return "ct", "CT"
    skip = re.search(
        r"locali[sz]er|scout|survey|aahead|(^|[^a-z])(adc|fa|colfa|trace|tensor|sbref|"
        r"phase|swi|bold|fmri|rest|asl|perf|t2star)([^a-z]|$)|flair",
        t,
    )
    if skip:
        return (
            None,
            f"'{skip.group(0).strip('_- ')}' series are not used by preprocessing",
        )
    if re.search(r"dwi|dti|diff|dmri|hardi|multishell", t):
        return "dwi", "diffusion keyword"
    if re.search(r"t2", t):
        return "T2w", "T2 keyword"
    if re.search(r"t1|mprage|mp2rage|spgr|bravo|tfl", t):
        return "T1w", "T1 keyword"
    return None, "no modality keyword"


def _visible(name: str) -> bool:
    return not name.startswith(".")  # also drops AppleDouble "._*" files


def _lower_suffix(name: str, suffixes: Tuple[str, ...]) -> Optional[str]:
    lowered = name.lower()
    return next((s for s in suffixes if lowered.endswith(s)), None)


def tool_inspect_raw_data(args: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(os.path.expanduser(str(args.get("path", "")))).resolve()
    if not root.is_dir():
        raise ToolError(f"not a folder on this machine: {root}")
    entries: List[Dict[str, Any]] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if _visible(d))
        files = sorted(f for f in filenames if _visible(f))
        scanned += len(files)
        if scanned > 100_000:
            raise ToolError(
                "more than 100000 files; point inspect_raw_data at a subfolder"
            )
        dicoms: List[Dict[str, str]] = []
        for name in files:
            path = Path(dirpath) / name
            if _lower_suffix(name, NIFTI_SUFFIXES) or _lower_suffix(
                name, ARCHIVE_SUFFIXES
            ):
                kind = "nifti" if _lower_suffix(name, NIFTI_SUFFIXES) else "archive"
                guess, why = _guess_modality(name)
                entries.append(
                    {
                        "source": str(path),
                        "kind": kind,
                        "files": 1,
                        "guess": guess,
                        "why": why,
                    }
                )
            elif len(dicoms) < 500 and not _lower_suffix(name, SIDECAR_SUFFIXES):
                fields = _dicom_fields(path)
                if fields is not None:
                    dicoms.append(fields)
        if dicoms:
            series = sorted(
                {
                    d.get("SeriesDescription") or d.get("ProtocolName") or "?"
                    for d in dicoms
                }
            )
            modality_tags = {d.get("Modality", "") for d in dicoms}
            guesses = {
                _guess_modality(
                    s, next(iter(modality_tags)) if len(modality_tags) == 1 else ""
                )
                for s in series
            }
            guess, why = (
                next(iter(guesses)) if len(guesses) == 1 else (None, "mixed series")
            )
            if len(series) > 1:
                why += f"; the folder holds {len(series)} series and all of them are imported"
            entries.append(
                {
                    "source": dirpath,
                    "kind": "dicom",
                    "files": len(files),
                    "series": series,
                    "guess": guess,
                    "why": why,
                }
            )
    mapping: Dict[str, List[str]] = {}
    for entry in entries:
        if entry["guess"]:
            mapping.setdefault(entry["guess"], []).append(entry["source"])
    notes = [
        f"{m}: {len(p)} candidates -- ask the user which one to stage"
        for m, p in mapping.items()
        if len(p) > 1
    ]
    if "T1w" not in mapping:
        notes.append("No T1w candidate found; preprocessing (charm) needs a T1w.")
    return {
        "root": str(root),
        "entries": entries,
        "proposed_mapping": mapping,
        "notes": notes,
        "next": "Confirm the mapping with the user, then call stage_raw_data.",
    }


def _host_project() -> Path:
    conn = _conn()
    host = conn.get("host_project") or _api("GET", "/api/project").get("host_path")
    if not host or not os.path.isdir(host):
        raise ToolError(
            f"the project folder ({host or 'unknown'}) is not visible from this machine, so raw "
            "data cannot be staged from here"
        )
    return Path(host).resolve()


def _staging_pairs(src: Path, dest_dir: Path) -> List[Tuple[Path, Path]]:
    if src.is_dir():
        pairs = []
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = [d for d in dirnames if _visible(d)]
            for name in filenames:
                if _visible(name):
                    file = Path(dirpath) / name
                    pairs.append((file, dest_dir / src.name / file.relative_to(src)))
        return pairs
    pairs = [(src, dest_dir / src.name)]
    nifti = _lower_suffix(src.name, NIFTI_SUFFIXES)
    if (
        nifti
    ):  # the gradient table and JSON travel with their image (dicom2nifti._copy_sidecars)
        stem = src.name[: -len(nifti)]
        for suffix in SIDECAR_SUFFIXES:
            sidecar = src.with_name(stem + suffix)
            if sidecar.is_file():
                pairs.append((sidecar, dest_dir / sidecar.name))
    return pairs


def tool_stage_raw_data(args: Dict[str, Any]) -> Dict[str, Any]:
    subject = _subject_id(args.get("subject_id"))
    mapping = args.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        raise ToolError(
            'mapping must be an object like {"T1w": ["/abs/path"], "dwi": [...]}'
        )
    project = _host_project()
    subject_dir = project / "sourcedata" / f"sub-{subject}"
    pairs: List[Tuple[Path, Path]] = []
    for modality, sources in mapping.items():
        canonical = MODALITIES.get(str(modality).lower())
        if canonical is None:
            raise ToolError(
                f"unknown modality {modality!r}; use one of T1w, T2w, ct, dwi"
            )
        for source in [sources] if isinstance(sources, str) else sources:
            src = Path(os.path.expanduser(str(source)))
            if not src.is_absolute() or not src.exists():
                raise ToolError(f"source must be an existing absolute path: {source}")
            src = src.resolve()
            sourcedata = project / "sourcedata"
            if (
                src == sourcedata
                or sourcedata in src.parents
                or src in subject_dir.parents
            ):
                raise ToolError(
                    f"{src} overlaps the staging area; stage from somewhere else"
                )
            pairs.extend(_staging_pairs(src, subject_dir / canonical))
    if not pairs:
        raise ToolError("nothing to copy (the sources hold no visible files)")
    seen = set()
    for _, dest in pairs:
        real = os.path.realpath(dest)
        if not real.startswith(str(subject_dir.resolve()) + os.sep):
            raise ToolError(f"refusing to write outside {subject_dir}: {dest}")
        if real in seen or os.path.lexists(dest):
            raise ToolError(
                f"{dest} already exists (or two sources share that name); nothing was copied. "
                "Staging never overwrites -- remove it yourself or stage under another subject id."
            )
        seen.add(real)
    copied_bytes = 0
    for src, dest in pairs:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied_bytes += dest.stat().st_size
    return {
        "subject_id": subject,
        "staged_files": len(pairs),
        "bytes": copied_bytes,
        "destination": str(subject_dir),
        "modalities": sorted({MODALITIES[str(m).lower()] for m in mapping}),
        "next": "submit_job(kind='pre', subject_ids=[...], config={'convert_dicom': true, "
        "'create_m2m': true, ...}) after plan_job.",
    }


# --------------------------------------------------------------------------
# Regions
# --------------------------------------------------------------------------

_SIDE_WORDS = {"left", "right", "bilateral", "both", "lh", "rh"}


def _side(name: str, hemi: Optional[str]) -> Optional[str]:
    if hemi in ("lh", "rh"):
        return "left" if hemi == "lh" else "right"
    n = name.lower()
    if re.search(r"(^|[^a-z])(left|lh|l)([^a-z]|$)", n):
        return "left"
    if re.search(r"(^|[^a-z])(right|rh|r)([^a-z]|$)", n):
        return "right"
    return None


def _roi(atlas: Dict[str, Any], regions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The FlexConfig ROI wire object the desktop builds (pages/_shared/roi/types.ts roiToConfig)."""
    if atlas.get("kind") == "surface":
        hemis = [r.get("hemi") or "lh" for r in regions]
        return {
            "_type": "AtlasROI",
            "atlas_path": [
                re.sub(r"(^|/)lh\.", rf"\g<1>{h}.", atlas["path"]) for h in hemis
            ],
            "label": [r["id"] for r in regions],
            "hemisphere": hemis,
        }
    return {
        "_type": "SubcorticalROI",
        "atlas_path": [atlas["path"]] * len(regions),
        "label": [r["id"] for r in regions],
        "tissues": "GM",
        "atlas_space": "subject",
    }


def tool_find_regions(args: Dict[str, Any]) -> Dict[str, Any]:
    subject = _subject_id(args.get("subject_id"))
    words = [w for w in re.findall(r"[a-z0-9]+", str(args.get("query", "")).lower())]
    words = [w for w in words if w not in _SIDE_WORDS]
    if not words:
        raise ToolError("query must name a structure, e.g. 'thalamus' or 'precentral'")
    found, skipped = [], []
    for atlas in _api("GET", "/api/catalog/atlases" + _q(subject=subject)) or []:
        try:
            regions = _api(
                "GET",
                "/api/catalog/atlases/regions" + _q(subject=subject, atlas=atlas["id"]),
            )
        except ToolError as exc:
            skipped.append(f"{atlas['id']}: {exc}")
            continue
        matches = [
            r
            for r in regions or []
            if all(w in re.sub(r"[^a-z0-9]", "", r["name"].lower()) for w in words)
        ]
        if not matches:
            continue
        for r in matches:
            r["side"] = _side(r["name"], r.get("hemi"))
        rois = {"all": _roi(atlas, matches)}
        for side in ("left", "right"):
            picked = [r for r in matches if r["side"] == side]
            if picked:
                rois[side] = _roi(atlas, picked)
        found.append(
            {
                "atlas": atlas["id"],
                "kind": atlas.get("kind"),
                "matches": matches[:60],
                "rois": rois,
            }
        )
    if not found:
        raise ToolError(
            f"no region of sub-{subject}'s atlases matches {args.get('query')!r}"
            + (f" (skipped: {'; '.join(skipped)})" if skipped else "")
            + ". Atlases exist only after preprocessing (charm/FastSurfer); try another "
            "spelling or ask the user for coordinates (SphericalROI)."
        )
    return {
        "subject_id": subject,
        "query": args.get("query"),
        "atlases": found,
        "skipped": skipped,
        "how_to_use": "Copy one rois.* object verbatim into FlexConfig.roi. 'all' is the union "
        "of every match (both sides, i.e. bilateral); 'left'/'right' are one side. Surface "
        "(AtlasROI) targets cortex, volume (SubcorticalROI) targets deep structures.",
    }


# --------------------------------------------------------------------------
# Schema, plan, submit
# --------------------------------------------------------------------------


def _refs(node: Any, out: set) -> set:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            out.add(ref.split("/")[-1])
        for value in node.values():
            _refs(value, out)
    elif isinstance(node, list):
        for value in node:
            _refs(value, out)
    return out


def tool_get_config_schema(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(args.get("kind", ""))
    name = SCHEMA_CLASS.get(kind, kind)
    defs = (_api("GET", "/api/schema") or {}).get("$defs", {})
    if name not in defs:
        raise ToolError(
            f"unknown kind/config class {kind!r}; kinds: {', '.join(SCHEMA_CLASS)}"
        )
    wanted, todo = {name}, [name]
    while todo:
        for ref in _refs(defs[todo.pop()], set()):
            if ref in defs and ref not in wanted:
                wanted.add(ref)
                todo.append(ref)
    out: Dict[str, Any] = {"class": name, "schema": defs[name]}
    out["$defs"] = {k: defs[k] for k in sorted(wanted - {name})}
    if kind in FLEX_KINDS:
        out["app_defaults_filled_in"] = FLEX_UI_DEFAULTS
    elif kind == "sim":
        out["app_defaults_filled_in"] = SIM_UI_DEFAULTS
    elif kind == "pre":
        out["app_defaults_filled_in"] = PRE_UI_DEFAULTS
    return out


def _with_app_defaults(kind: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if kind == "pre":
        return {**PRE_UI_DEFAULTS, **config}
    if kind == "sim":
        return {**SIM_UI_DEFAULTS, **config}
    if kind not in FLEX_KINDS:
        return dict(config)
    merged = {**FLEX_UI_DEFAULTS, **config}
    merged["electrode"] = {
        **FLEX_UI_DEFAULTS["electrode"],
        **(config.get("electrode") or {}),
    }
    if (
        merged["goal"] in ("focality", "focality_tf")
        and merged["non_roi_method"] is None
    ):
        merged["non_roi_method"] = "everything_else"
    if kind == "flex_adaptive" and not merged.get("adaptive"):
        merged["adaptive"] = {"nonroi_percentage": 20, "roi_percentage": 80}
    if kind == "flex_pareto" and not merged.get("pareto"):
        merged["pareto"] = {"roi_pcts": [80], "nonroi_pcts": [20, 30, 40]}
    return merged


def _flex_output_folder(kind: str, config: Dict[str, Any], subject: str) -> str:
    """An absolute run folder, as the Optimizer page resolves one before submitting.

    A bare name goes under the subject's flex-search folder; none at all gets a timestamp
    name, so the run's folder is known before the job starts.
    """
    name = str(config.get("output_folder") or "").strip()
    if name.startswith("/"):
        return name
    if "/" in name or "\\" in name or name in (".", ".."):
        raise ToolError(
            "output_folder must be a run name without separators, or absolute"
        )
    probe = _api(
        "POST",
        f"/api/plan/{kind}",
        {
            "config": {**config, "subject_id": subject, "output_folder": None},
            "subject_ids": [subject],
        },
    )
    parent = os.path.dirname(probe["jobs"][0]["output_dir"])
    return f"{parent}/{name or time.strftime('%Y%m%d_%H%M%S') + '_agent'}"


def _prepare(
    kind: str, config: Any, subject_ids: List[str]
) -> List[Tuple[str, Dict[str, Any]]]:
    """One ``(subject, config)`` per job, with app defaults and the subject's own id filled in."""
    if not isinstance(config, dict):
        raise ToolError("config must be an object")
    config = _with_app_defaults(kind, config)
    if kind == "pre":
        return [("", {**config, "subject_ids": subject_ids})]
    entries = []
    for sid in subject_ids:
        entry = {**config, "subject_id": sid}
        if kind in FLEX_KINDS:
            entry["output_folder"] = _flex_output_folder(kind, entry, sid)
        entries.append((sid, entry))
    return entries


def _plan(
    kind: str, entries: List[Tuple[str, Dict[str, Any]]], overwrite: bool
) -> Dict[str, Any]:
    plans, errors, missing = [], [], []
    for sid, config in entries:
        subjects = [sid] if sid else config["subject_ids"]
        check = _api("POST", f"/api/validate/{kind}", {"config": config})
        if not check.get("ok"):
            errors.extend(check.get("errors") or [])
            continue
        missing.extend(
            _api(
                "POST",
                "/api/jobs/preflight",
                {"kind": kind, "config": config, "subject_ids": subjects},
            ).get("missing", [])
        )
        plans.append(
            _api(
                "POST",
                f"/api/plan/{kind}",
                {"config": config, "subject_ids": subjects, "overwrite": overwrite},
            )
        )
    jobs = [j for p in plans for j in p.get("jobs", [])]
    eta = [p["cost"].get("eta_minutes") for p in plans if p.get("cost")]
    return {
        "ok": not errors and not missing,
        "errors": errors,
        "missing_inputs": missing,
        "jobs": jobs,
        "will_overwrite": [j["output_dir"] for j in jobs if j.get("will_overwrite")],
        "lock_conflicts": [c for p in plans for c in p.get("lock_conflicts", [])],
        "eta_minutes": sum(e for e in eta if e) if any(eta) else None,
        "warnings": [w for p in plans for w in p.get("warnings", [])],
        "resolved": [p.get("resolved") for p in plans if p.get("resolved")],
    }


def tool_plan_job(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(args.get("kind", ""))
    entries = _prepare(kind, args.get("config"), _subject_ids(args.get("subject_ids")))
    result = _plan(kind, entries, bool(args.get("overwrite", False)))
    if result["will_overwrite"] and not args.get("overwrite"):
        result["next"] = (
            "Existing output would be replaced: ask the user, then submit with overwrite=true, "
            "or change the run name."
        )
    return result


def _submit(
    kind: str,
    entries: List[Tuple[str, Dict[str, Any]]],
    subject_ids: List[str],
    overwrite: bool,
    after: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if (
        kind in GROUP_KINDS and not after
    ):  # what every run page sends (pages/_shared/run)
        body: Dict[str, Any] = {
            "kind": kind,
            "config": entries[0][1],
            "subject_ids": subject_ids,
            "created_by": CREATED_BY,
        }
        if kind != "pre":
            body["subject_configs"] = [
                {"subject_id": s, "config": c} for s, c in entries
            ]
        if len(entries) > 1 and kind != "pre":
            body["tags"] = [f"{kind}-batch"]
        if overwrite:
            body["overwrite"] = True
        result = _api("POST", "/api/jobs/groups", body)
        jobs = result.get("jobs", [])
        group = result.get("group_id")
    else:
        jobs, group = [], None
        for sid, config in entries:
            body = {
                "kind": kind,
                "config": config,
                "subject_ids": [sid] if sid else subject_ids,
                "created_by": CREATED_BY,
            }
            if after:
                body["after"] = after
            if overwrite:
                body["overwrite"] = True
            jobs.append(_api("POST", "/api/jobs", body))
    out: Dict[str, Any] = {
        "group_id": group,
        "jobs": [_job_summary(j) for j in jobs],
        "job_ids": [j["id"] for j in jobs],
        "next": "wait_for_job(job_ids=...) -- call again while any job is still running.",
    }
    if kind in FLEX_KINDS:
        out["output_folders"] = {s: c["output_folder"] for s, c in entries}
    return out


def tool_submit_job(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(args.get("kind", ""))
    subject_ids = _subject_ids(args.get("subject_ids"))
    after = args.get("after") or None
    if after is not None and not (
        isinstance(after, list) and all(isinstance(a, str) for a in after)
    ):
        raise ToolError("after must be a list of job ids")
    if after and kind == "pre":
        raise ToolError("kind='pre' cannot wait on other jobs; submit it on its own")
    entries = _prepare(kind, args.get("config"), subject_ids)
    return _submit(
        kind, entries, subject_ids, bool(args.get("overwrite", False)), after
    )


# --------------------------------------------------------------------------
# wait / cancel
# --------------------------------------------------------------------------


def _finished(job_id: str, status: Dict[str, Any]) -> Dict[str, Any]:
    out = _job_summary(status)
    failed = status.get("state") != "succeeded"
    quoted = urllib.parse.quote(job_id, safe="")
    log = _api(
        "GET", f"/api/jobs/{quoted}/log" + _q(tail=40 if failed else 10), text=True
    )
    out["log_tail"] = log.splitlines()[-(40 if failed else 10) :]
    outputs = _api("GET", f"/api/jobs/{quoted}/artifacts") or {}
    files = outputs.get("files") or []
    out["output_folder"] = outputs.get("folder")
    out["output_files"] = [
        {"label": f.get("label"), "kind": f.get("kind"), "path": f.get("path")}
        for f in files[:40]
    ]
    if len(files) > 40:
        out["output_files_truncated"] = len(files)
    return out


def tool_wait_for_job(args: Dict[str, Any]) -> Dict[str, Any]:
    ids = args.get("job_ids") or args.get("job_id")
    ids = [ids] if isinstance(ids, str) else ids
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        raise ToolError("job_ids must be a non-empty list of job ids")
    timeout = min(max(float(args.get("timeout_s", 50)), 0.0), 600.0)
    poll = float(os.environ.get("TIT_AGENT_POLL_S", "3"))
    deadline = time.monotonic() + timeout
    while True:
        statuses = {
            i: _api("GET", f"/api/jobs/{urllib.parse.quote(i, safe='')}")["status"]
            for i in ids
        }
        pending = [
            i for i, s in statuses.items() if s.get("state") not in TERMINAL_STATES
        ]
        if not pending or time.monotonic() >= deadline:
            break
        time.sleep(min(poll, max(deadline - time.monotonic(), 0.0)))
    return {
        "done": not pending,
        "jobs": [
            _job_summary(s) if i in pending else _finished(i, s)
            for i, s in statuses.items()
        ],
        "next": (
            "Still running: call wait_for_job again."
            if pending
            else "All finished. Report states and output paths to the user."
        ),
    }


def tool_cancel_job(args: Dict[str, Any]) -> Dict[str, Any]:
    job_id = str(args.get("job_id", ""))
    if not job_id:
        raise ToolError("job_id is required")
    return _job_summary(
        _api("POST", f"/api/jobs/{urllib.parse.quote(job_id, safe='')}/cancel")
    )


# --------------------------------------------------------------------------
# flex result -> simulation (what Simulator > flex row does, in one call)
# --------------------------------------------------------------------------


def tool_simulate_flex_result(args: Dict[str, Any]) -> Dict[str, Any]:
    subject = _subject_id(args.get("subject_id"))
    # The server owns the run -> montage resolution (tit.sim.montage_sources
    # .resolve_flex_simulation), the same one an approved proposal's sim_from_flex step uses.
    found = _api(
        "GET",
        "/api/sim-from-flex"
        + _q(
            subject=subject, flex_run=args.get("flex_run"), eeg_net=args.get("eeg_net")
        ),
    )
    intensities = args.get("intensities") or found["intensities"]
    config = {
        **(args.get("overrides") or {}),
        "montages": [found["montage"]],
        "intensities": intensities,
    }
    entries = _prepare("sim", config, [subject])
    overwrite = bool(args.get("overwrite", False))
    plan = _plan("sim", entries, overwrite)
    out: Dict[str, Any] = {
        "flex_run": found["flex_run"],
        "placement": found["placement"],
        "intensities_mA": intensities,
        "intensities_from": (
            "given" if args.get("intensities") else found["intensities_from"]
        ),
        "plan": plan,
    }
    if not plan["ok"]:
        out["submitted"] = False
        return out
    if plan["will_overwrite"] and not overwrite:
        out["submitted"] = False
        out["next"] = (
            "A simulation of this run exists: ask the user, then repeat with overwrite=true."
        )
        return out
    if args.get("dry_run"):
        out["submitted"] = False
        return out
    out.update(_submit("sim", entries, [subject], overwrite))
    out["submitted"] = True
    return out


# --------------------------------------------------------------------------
# Proposals: the agent proposes, the user approves in the app, the app queues
# --------------------------------------------------------------------------

#: initialize's clientInfo.name -> the name the approval card shows.
CLIENT_LABELS = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "codex-mcp-client": "Codex",
}
_CLIENT: Optional[str] = None


def _step_for_proposal(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ToolError("each step must be an object")
    kind = str(raw.get("kind", ""))
    config = raw.get("config") or {}
    if not isinstance(config, dict):
        raise ToolError(f"step {raw.get('id')}: config must be an object")
    if kind == "sim_from_flex":  # the run's own currents unless the agent names some
        defaults = {k: v for k, v in SIM_UI_DEFAULTS.items() if k != "intensities"}
        config = {**defaults, **config}
    else:
        config = _with_app_defaults(kind, config)
    config.pop("subject_ids", None)  # the step's subject_ids decide
    return {
        **{k: raw[k] for k in ("id", "note", "overwrite", "after") if k in raw},
        "kind": kind,
        "config": config,
        "subject_ids": _subject_ids(raw.get("subject_ids")),
    }


def _step_summary(step: Dict[str, Any]) -> Dict[str, Any]:
    plan = step.get("plan") or {}
    out = {
        "id": step["id"],
        "kind": step["kind"],
        "subject_ids": step["subject_ids"],
        "state": step.get("state"),
        "job_ids": step.get("job_ids") or [],
    }
    for key in (
        "errors",
        "missing_inputs",
        "will_overwrite",
        "deferred",
        "eta_minutes",
    ):
        if plan.get(key):
            out[key] = plan[key]
    outputs = [o["output_dir"] for o in plan.get("outputs") or []]
    if outputs:
        out["output_dirs"] = outputs
    for key in ("error", "skipped", "resolved"):
        if step.get(key):
            out[key] = step[key]
    return out


def tool_propose_pipeline(args: Dict[str, Any]) -> Dict[str, Any]:
    raw_steps = args.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ToolError("steps must be a non-empty list")
    body: Dict[str, Any] = {
        "title": args.get("title"),
        "rationale": args.get("rationale") or "",
        "steps": [_step_for_proposal(s) for s in raw_steps],
        "created_by": CREATED_BY,
        "client": CLIENT_LABELS.get(str(_CLIENT or "").lower(), _CLIENT),
    }
    draft = _api("POST", "/api/proposals", {**body, "dry_run": True})
    steps = [_step_summary(s) for s in draft["steps"]]
    blocking = [s for s in steps if s.get("errors") or s.get("missing_inputs")]
    if blocking:
        return {
            "proposed": False,
            "steps": steps,
            "next": "Nothing was shown to the user. Fix the errors / missing inputs above "
            "(run a 'pre' step first for missing head models) and call propose_pipeline again.",
        }
    created = _api("POST", "/api/proposals", body)
    out: Dict[str, Any] = {
        "proposed": True,
        "proposal_id": created["id"],
        "status": created["status"],
        "steps": [_step_summary(s) for s in created["steps"]],
        "next": "Tell the user the plan is waiting for their approval in TI-Toolbox (Jobs "
        "page), then call wait_for_approval(proposal_id). Do not submit these jobs yourself.",
    }
    if any(s.get("will_overwrite") for s in steps):
        out["note"] = (
            "Some steps would replace existing output: approval needs the user to allow "
            "replacing on the card (or edit the run name)."
        )
    return out


def _quoted(proposal_id: Any) -> str:
    if not isinstance(proposal_id, str) or not proposal_id:
        raise ToolError("proposal_id is required")
    return urllib.parse.quote(proposal_id, safe="")


def tool_wait_for_approval(args: Dict[str, Any]) -> Dict[str, Any]:
    path = f"/api/proposals/{_quoted(args.get('proposal_id'))}"
    timeout = min(max(float(args.get("timeout_s", 50)), 0.0), 600.0)
    poll = float(os.environ.get("TIT_AGENT_POLL_S", "3"))
    deadline = time.monotonic() + timeout
    while True:
        proposal = _api("GET", path)
        if proposal["decision"]["state"] != "pending" or time.monotonic() >= deadline:
            break
        time.sleep(min(poll, max(deadline - time.monotonic(), 0.0)))
    decision = proposal["decision"]
    out: Dict[str, Any] = {"decision": decision["state"], "note": decision.get("note")}
    if decision["state"] == "pending":
        out["next"] = "Still waiting for the user: call wait_for_approval again."
    elif decision["state"] == "rejected":
        out["next"] = (
            "The user rejected the plan. Tell them, quote their note, and ask what to change; "
            "never propose the same plan again unchanged."
        )
    else:
        proposed = {s["id"]: s for s in proposal["proposed_steps"]}
        out["edited_by_user"] = proposal.get("edited", False)
        out["steps"] = []
        for step in proposal["steps"]:
            summary = _step_summary(step)
            original = proposed.get(step["id"]) or {}
            if (step["config"], step["subject_ids"], step["overwrite"]) != (
                original.get("config"),
                original.get("subject_ids"),
                original.get("overwrite"),
            ):
                summary["edited"] = True
                summary["approved_config"] = step["config"]
            out["steps"].append(summary)
        out["next"] = (
            "Approved: the app queued the steps itself (later steps start when the ones they "
            "wait on succeed). Follow with wait_for_job(job_ids) and get_proposal; report what "
            "the user changed, if anything."
        )
    return out


def tool_get_proposal(args: Dict[str, Any]) -> Dict[str, Any]:
    proposal = _api("GET", f"/api/proposals/{_quoted(args.get('proposal_id'))}")
    return {
        "proposal_id": proposal["id"],
        "title": proposal["title"],
        "status": proposal["status"],
        "decision": proposal["decision"],
        "steps": [_step_summary(s) for s in proposal["steps"]],
    }


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------


def _schema(props: Dict[str, Any], required: Tuple[str, ...] = ()) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": list(required),
        "additionalProperties": False,
    }


def _hints(
    read_only: bool, destructive: bool = False, idempotent: bool = False
) -> Dict[str, Any]:
    hints: Dict[str, Any] = {"readOnlyHint": read_only, "openWorldHint": False}
    if not read_only:
        hints.update(destructiveHint=destructive, idempotentHint=idempotent)
    return hints


_STR = {"type": "string"}
_SUBJECTS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "ids without 'sub-'",
}
_KIND = {
    "type": "string",
    "description": "pre, sim, flex, flex_adaptive, flex_pareto, ex, mex, leadfield, analyzer, ...",
}

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "connect",
        "description": "Call first. Finds the TI-Toolbox the user has open and returns its "
        "project folder, every subject with what it has (has_raw, has_sourcedata, has_m2m, ...) "
        "and the jobs queued or running. Pass project=<host path> only when several projects "
        "are open.",
        "inputSchema": _schema({"project": _STR}),
        "annotations": _hints(True),
        "handler": tool_connect,
    },
    {
        "name": "inspect_raw_data",
        "description": "Look at a folder of raw scans on this computer (DICOM series, NIfTI, "
        "archives), guess each one's modality (T1w/T2w/ct/dwi) and propose a staging mapping. "
        "Reads only.",
        "inputSchema": _schema({"path": _STR}, ("path",)),
        "annotations": _hints(True),
        "handler": tool_inspect_raw_data,
    },
    {
        "name": "stage_raw_data",
        "description": "Copy (never move, never overwrite) raw scans into the project's "
        "sourcedata/sub-<id>/<modality>/ so preprocessing with convert_dicom can import them. "
        "mapping is {modality: [absolute file or folder paths]} with modality T1w, T2w, ct or dwi.",
        "inputSchema": _schema(
            {
                "subject_id": _STR,
                "mapping": {
                    "type": "object",
                    "additionalProperties": {
                        "anyOf": [_STR, {"type": "array", "items": _STR}]
                    },
                },
            },
            ("subject_id", "mapping"),
        ),
        "annotations": _hints(False, destructive=False),
        "handler": tool_stage_raw_data,
    },
    {
        "name": "find_regions",
        "description": "Search one subject's atlases for a structure (e.g. 'thalamus', "
        "'precentral') and return ready-to-use FlexConfig ROI objects: rois.all (bilateral "
        "union), rois.left, rois.right. Never invent atlas paths or label ids -- use these.",
        "inputSchema": _schema(
            {"subject_id": _STR, "query": _STR}, ("subject_id", "query")
        ),
        "annotations": _hints(True),
        "handler": tool_find_regions,
    },
    {
        "name": "get_config_schema",
        "description": "JSON schema of one job kind's config (with referenced definitions) and "
        "the app defaults this server fills in for omitted fields.",
        "inputSchema": _schema({"kind": _KIND}, ("kind",)),
        "annotations": _hints(True),
        "handler": tool_get_config_schema,
    },
    {
        "name": "plan_job",
        "description": "Validate a config and show what submitting it would do: errors, missing "
        "inputs, output folders, which existing outputs would be replaced, lock waits and ETA. "
        "Always call before submit_job. Same arguments as submit_job.",
        "inputSchema": _schema(
            {
                "kind": _KIND,
                "config": {"type": "object"},
                "subject_ids": _SUBJECTS,
                "overwrite": {"type": "boolean"},
            },
            ("kind", "config", "subject_ids"),
        ),
        "annotations": _hints(True),
        "handler": tool_plan_job,
    },
    {
        "name": "submit_job",
        "description": "Queue a job directly, without the user's approval. Only works when the "
        "user turned on 'Agent may submit without approval' in the app (connect reports "
        "approval_required=false); otherwise the app refuses it (HTTP 403) and you must use "
        "propose_pipeline. One job per subject; kind='pre' queues the full preprocessing stage "
        "graph. Omitted fields take the app's defaults; subject_id is filled per subject. "
        "overwrite=true replaces existing output -- only after the user agreed. after=[job ids] "
        "waits for other jobs.",
        "inputSchema": _schema(
            {
                "kind": _KIND,
                "config": {"type": "object"},
                "subject_ids": _SUBJECTS,
                "overwrite": {"type": "boolean"},
                "after": {"type": "array", "items": _STR},
            },
            ("kind", "config", "subject_ids"),
        ),
        "annotations": _hints(False, destructive=True),
        "handler": tool_submit_job,
    },
    {
        "name": "wait_for_job",
        "description": "Wait up to timeout_s (default 50, max 600) for jobs to finish. Returns each "
        "job's state; finished jobs also get their log tail, output folder and files. Call again "
        "while done=false -- preprocessing and optimisation take tens of minutes.",
        "inputSchema": _schema(
            {
                "job_ids": {"type": "array", "items": _STR},
                "timeout_s": {"type": "number"},
            },
            ("job_ids",),
        ),
        "annotations": _hints(True),
        "handler": tool_wait_for_job,
    },
    {
        "name": "cancel_job",
        "description": "Cancel a queued or running job (stops its processes).",
        "inputSchema": _schema({"job_id": _STR}, ("job_id",)),
        "annotations": _hints(False, destructive=True, idempotent=True),
        "handler": tool_cancel_job,
    },
    {
        "name": "simulate_flex_result",
        "description": "Simulate a finished flex-search run's electrodes, as the Simulator does "
        "for a flex row: picks the run (default: newest), the placement (eeg_net, else the "
        "first mapped net, else the optimised XYZ), the run's own currents, plans, and submits "
        "unless it would overwrite (then asks for overwrite=true). overrides merges extra "
        "SimulationConfig fields. Submitting needs approval_required=false; otherwise use "
        "dry_run=true to preview and propose a sim_from_flex step with config.flex_run.",
        "inputSchema": _schema(
            {
                "subject_id": _STR,
                "flex_run": _STR,
                "eeg_net": _STR,
                "intensities": {"type": "array", "items": {"type": "number"}},
                "overrides": {"type": "object"},
                "overwrite": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
            },
            ("subject_id",),
        ),
        "annotations": _hints(False, destructive=True),
        "handler": tool_simulate_flex_result,
    },
    {
        "name": "propose_pipeline",
        "description": "Propose a plan for the user to approve in the app (a card on its Jobs "
        "page). steps run in order: each {id, kind, config, subject_ids, after?: [earlier step "
        "ids], note?, overwrite?}. kind is a job kind or 'sim_from_flex' (config.flex_step = an "
        "earlier flex step's id, or config.flex_run = a finished run's name; optional eeg_net, "
        "intensities and SimulationConfig fields). Omitted fields take the app's defaults; a "
        "flex step without output_folder gets a timestamped run name. The server validates and "
        "plans every step first; with errors nothing is shown to the user. After approval the "
        "app queues the steps itself -- a step starts when every step in its after succeeded.",
        "inputSchema": _schema(
            {
                "title": _STR,
                "rationale": {
                    "type": "string",
                    "description": "why this plan, in the user's terms",
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": _STR,
                            "kind": _KIND,
                            "config": {"type": "object"},
                            "subject_ids": _SUBJECTS,
                            "after": {"type": "array", "items": _STR},
                            "note": _STR,
                            "overwrite": {"type": "boolean"},
                        },
                        "required": ["id", "kind", "config", "subject_ids"],
                    },
                },
            },
            ("title", "rationale", "steps"),
        ),
        "annotations": _hints(False, destructive=False),
        "handler": tool_propose_pipeline,
    },
    {
        "name": "wait_for_approval",
        "description": "Wait up to timeout_s (default 50, max 600) for the user to approve or "
        "reject a proposal. Approved: each step with its job ids and, where the user edited it, "
        "the config that will run. Rejected: the user's note. Call again while pending.",
        "inputSchema": _schema(
            {"proposal_id": _STR, "timeout_s": {"type": "number"}}, ("proposal_id",)
        ),
        "annotations": _hints(True),
        "handler": tool_wait_for_approval,
    },
    {
        "name": "get_proposal",
        "description": "A proposal's status and each step's state (proposed, waiting, queued, "
        "running, succeeded, failed, skipped, error) with its job ids.",
        "inputSchema": _schema({"proposal_id": _STR}, ("proposal_id",)),
        "annotations": _hints(True),
        "handler": tool_get_proposal,
    },
]

_HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    t["name"]: t["handler"] for t in TOOLS
}


# --------------------------------------------------------------------------
# JSON-RPC / MCP plumbing (same wire behaviour as server.py)
# --------------------------------------------------------------------------


def _result(id_: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _text(id_: Any, text: str, is_error: bool) -> Dict[str, Any]:
    return _result(
        id_, {"content": [{"type": "text", "text": text}], "isError": is_error}
    )


def handle(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method, id_ = msg.get("method"), msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        global _CLIENT
        _CLIENT = (params.get("clientInfo") or {}).get("name") or None
        return _result(
            id_,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Runs TI-Toolbox jobs through the app the user has open; every job appears "
                    "live in its job list. Call connect first: unless it says "
                    "approval_required is false, jobs need the user's approval -- propose the "
                    "whole pipeline with propose_pipeline, wait_for_approval, then follow the "
                    "queued jobs with wait_for_job / get_proposal. Raw scans: inspect_raw_data "
                    "-> confirm -> stage_raw_data. Targets: find_regions, never invented atlas "
                    "paths or labels. Plan before proposing or submitting; never resubmit a "
                    "rejected plan unchanged."
                ),
            },
        )
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(
            id_,
            {"tools": [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS]},
        )
    if method == "tools/call":
        fn = _HANDLERS.get(params.get("name"))
        if fn is None:
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "error": {
                    "code": -32602,
                    "message": f"Unknown tool: {params.get('name')}",
                },
            }
        try:
            out = fn(params.get("arguments") or {})
            return _text(id_, json.dumps(out, indent=2, ensure_ascii=False), False)
        except ToolError as exc:
            return _text(id_, str(exc), True)
        except Exception as exc:  # noqa: BLE001 - report, never crash the server
            return _text(id_, f"{type(exc).__name__}: {exc}", True)
    if id_ is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve() -> None:
    for raw in sys.stdin.buffer:
        line = raw.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
        except json.JSONDecodeError:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        if resp is not None:
            sys.stdout.buffer.write(
                (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
            )
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    serve()
