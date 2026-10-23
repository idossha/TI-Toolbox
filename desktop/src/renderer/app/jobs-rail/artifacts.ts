/**
 * What a job's artifact rows offer — the rules, as pure functions, so the unit test can read them
 * without a DOM.
 *
 * The tab used to give every row a `View` (open the raw file in a browser tab) and an `↗ Open`
 * (reveal it natively). The maintainer's review: *"remove the View from the artifact section. Also,
 * instead of having the Open next to every element, just have the Open at the bottom of the list
 * because all artefacts are within the same folder. Specifically for the mesh, we can keep a 'view
 * in Tetravox' option."* So: no `View`, no per-row `Open`, one **Open folder** under the list, and
 * an **Open in Tetravox** only on the rows a scene can actually draw.
 */
import type { JobStatus } from "./api";
import type { ViewerLink } from "../openInViewer";

/**
 * Whether a scene can draw this file, by name.
 *
 * `tit/catalog.py::classify_view_file` is the authority on the seven scene kinds, and this is the
 * subset of its rules for the three a job ever writes: a tetrahedral mesh, a volume, a surface.
 * It is restated here rather than fetched because it is a suffix test on a string the payload
 * already carries, and a round trip per row would make the tab wait on the network to draw a
 * button. The two must agree; `tests/unit/job-artifacts.test.ts` pins the cases that matter.
 *
 * `.opt` is the explicit exclusion: `roi_overlay.msh.opt` is a Gmsh *options* file that sits beside
 * the mesh and has nothing in it to view. It ends in neither a mesh nor a volume suffix, so the
 * suffix test already refuses it — the early return says so out loud, because "the row next to the
 * mesh also offered Tetravox" is exactly the confusion this list is being cleaned up to remove.
 */
export function viewableKind(path: string): "mesh" | "volume" | "surface" | "scene" | null {
  const lowered = path.toLowerCase();
  if (lowered.endsWith(".opt")) return null;
  // A saved scene is the one artifact that needs no scene built for it: it *is* one. Every
  // optimization leaves a `roi.tetravox.json` naming the ROI it is about (`tit/roi_confirmation.py`)
  // and every analysis a `scene.tetravox.json` of its field masked to the ROI
  // (`tit/analyzer/scene.py`), and that row is the one a person most wants this button on.
  if (lowered.endsWith(".tetravox.json")) return "scene";
  if (lowered.endsWith(".msh")) return "mesh";
  if (lowered.endsWith(".nii") || lowered.endsWith(".nii.gz") || lowered.endsWith(".mgz")) return "volume";
  if (lowered.endsWith(".gii") || lowered.endsWith(".surf.gii")) {
    // A data-GIfTI carries per-vertex numbers *for* a surface and is not geometry on its own.
    return /\.(func|shape|time)\.gii$/.test(lowered) ? null : "surface";
  }
  return null;
}

/**
 * The folder the job's registered artifacts point at, or null when it has registered none: the
 * `dir` artifact itself (a simulation registers `Simulations/<montage>/`, a flex search its run
 * folder — that path IS the folder, not a file inside it), else the directory of the first file.
 * The same rule `JobManager.get_outputs` applies to build the Artifacts tab's list.
 *
 * It is never the folder of `log_path` (`code/ti-toolbox/jobs/<id>/`, the job's bookkeeping
 * record), and it is empty until the runner reports something, so it is not what a folder button
 * opens: that is `output_dir` from the server, via `useJobFolder`.
 */
export function jobFolder(job: JobStatus): string | null {
  const registered = job.artifacts.filter((a) => a.path);
  const dir = registered.find((a) => a.kind === "dir");
  if (dir) return dir.path;
  const first = registered[0]?.path;
  if (!first) return null;
  const cut = first.lastIndexOf("/");
  return cut > 0 ? first.slice(0, cut) : null;
}

/**
 * The viewer link one artifact of one job stands for.
 *
 * `kind: "custom"` — the Viewer's file-list view, whose only required control is the `path` this
 * button was pressed on. That is the whole point of the gesture: a person clicked *this mesh* and
 * asked to see *this mesh*, and `custom` is the one view type that means exactly that. The richer
 * per-kind scenes (`analysis` wants a simulation *and* an analysis; `simulation` wants a
 * simulation and a field) need controls a job's artifact list does not carry, and a link that
 * names a kind whose controls it cannot fill is refused before the wire as an incomplete
 * selection — which is how this arrived as a button that did nothing.
 *
 * The subject still rides along so the shell's subject switcher re-scopes with the navigation, and
 * so "back to the Menu" is scoped to the person whose file is on screen.
 *
 * `undefined` when the row is not something a scene can draw.
 */
export function viewerLinkForArtifact(job: JobStatus, path: string): ViewerLink | undefined {
  if (viewableKind(path) === null) return undefined;
  return { subject: job.subject_ids[0] ?? "", kind: "custom", path, open: true };
}
