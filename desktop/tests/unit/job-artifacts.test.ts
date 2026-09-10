/**
 * The rules behind the Jobs ▸ Artifacts tab's row actions.
 *
 * Maintainer review: no `View`, no per-row `Open`, one `Open folder` under the list, and
 * "Open in Tetravox" only on a row a scene can actually draw. These are the three pure functions
 * that decide it; the e2e checks the buttons those decisions produce.
 */
import { describe, expect, it } from "vitest";
import { jobFolder, viewableKind, viewerLinkForArtifact } from "../../src/renderer/app/jobs-rail/artifacts";
import type { JobStatus } from "../../src/renderer/app/jobs-rail/api";

const JOB_DIR = "/mnt/project/code/ti-toolbox/jobs/j-1";

function job(patch: Partial<JobStatus> = {}): JobStatus {
  return {
    id: "j-1",
    kind: "analyzer",
    state: "succeeded",
    subject_ids: ["ernie"],
    created_at: "2026-09-07T12:00:00Z",
    artifacts: [
      { path: `${JOB_DIR}/analysis.json`, kind: "json" },
      { path: `${JOB_DIR}/histogram_histogram.pdf`, kind: "pdf" },
      { path: `${JOB_DIR}/results.csv`, kind: "csv" },
      { path: `${JOB_DIR}/roi_overlay.msh`, kind: "mesh" },
      { path: `${JOB_DIR}/roi_overlay.msh.opt`, kind: "txt" },
    ],
    log_path: `${JOB_DIR}/stdout.log`,
    ...patch,
  } as JobStatus;
}

describe("viewableKind", () => {
  it("names the three kinds a job writes that a scene can draw", () => {
    expect(viewableKind("/p/roi_overlay.msh")).toBe("mesh");
    expect(viewableKind("/p/TI_max.nii.gz")).toBe("volume");
    expect(viewableKind("/p/T1.nii")).toBe("volume");
    expect(viewableKind("/p/orig.mgz")).toBe("volume");
    expect(viewableKind("/p/lh.central.gii")).toBe("surface");
  });

  it("refuses the Gmsh options file that sits beside a mesh", () => {
    // The row the maintainer's screenshot showed directly under `roi_overlay.msh`. It is not a
    // mesh, there is nothing in it to draw, and offering Tetravox on it is the confusion this
    // tab is being cleaned up to remove.
    expect(viewableKind("/p/roi_overlay.msh.opt")).toBeNull();
  });

  it("refuses everything else a job writes", () => {
    for (const p of ["/p/analysis.json", "/p/results.csv", "/p/histogram.pdf", "/p/stdout.log", "/p/x.mat"]) {
      expect(viewableKind(p)).toBeNull();
    }
  });

  it("refuses a data-GIfTI, which is numbers for a surface rather than a surface", () => {
    expect(viewableKind("/p/lh.thickness.shape.gii")).toBeNull();
    expect(viewableKind("/p/lh.TI_max.func.gii")).toBeNull();
  });

  it("is case-insensitive, because a filename from a Windows-authored dataset is not lowercase", () => {
    expect(viewableKind("/p/ROI_OVERLAY.MSH")).toBe("mesh");
    expect(viewableKind("/p/T1.NII.GZ")).toBe("volume");
  });
});

describe("jobFolder", () => {
  it("is the job's own directory, taken from a path the job already reported", () => {
    expect(jobFolder(job())).toBe(JOB_DIR);
  });

  it("falls back to an artifact when there is no log path", () => {
    expect(jobFolder(job({ log_path: null }))).toBe(JOB_DIR);
  });

  it("is null for a job that has written nothing", () => {
    expect(jobFolder(job({ log_path: null, artifacts: [] }))).toBeNull();
  });
});

describe("viewerLinkForArtifact", () => {
  it("offers nothing for a row no scene can draw", () => {
    expect(viewerLinkForArtifact(job(), `${JOB_DIR}/results.csv`)).toBeUndefined();
    expect(viewerLinkForArtifact(job(), `${JOB_DIR}/roi_overlay.msh.opt`)).toBeUndefined();
  });

  it("asks for the file that was clicked, by path, on the job's subject", () => {
    // `custom` is the one view type whose only required control is the path. Naming a richer kind
    // (`analysis` needs a simulation *and* an analysis) produces a selection the Viewer refuses as
    // incomplete before it reaches the wire — a button that navigates and then does nothing.
    expect(viewerLinkForArtifact(job(), `${JOB_DIR}/roi_overlay.msh`)).toEqual({
      subject: "ernie",
      kind: "custom",
      path: `${JOB_DIR}/roi_overlay.msh`,
      open: true,
    });
  });

  it("still offers a project-wide job's artifact, with no subject to scope it to", () => {
    const j = job({ kind: "stats", subject_ids: [] } as Partial<JobStatus>);
    expect(viewerLinkForArtifact(j, `${JOB_DIR}/tstat.nii.gz`)?.path).toBe(`${JOB_DIR}/tstat.nii.gz`);
  });

  it("always asks the viewer to actually open, never to sit on the Menu", () => {
    // The maintainer's report about Results applies here too: a person who pressed a button
    // labelled "Open in Tetravox" asked to see the file.
    expect(viewerLinkForArtifact(job(), `${JOB_DIR}/roi_overlay.msh`)?.open).toBe(true);
  });
});

// -------------------------------------------------------------------------------------------------
// The link these rules produce, as a URL — the half the Viewer actually reads.
// -------------------------------------------------------------------------------------------------

describe("viewerSearch for a job artifact", () => {
  it("carries the file, the kind and the intent to open", async () => {
    const { viewerSearch } = await import("../../src/renderer/app/openInViewer");
    const link = viewerLinkForArtifact(job(), `${JOB_DIR}/roi_overlay.msh`)!;
    const params = new URLSearchParams(viewerSearch(link));
    expect(params.get("kind")).toBe("custom");
    expect(params.get("subject")).toBe("ernie");
    expect(params.get("path")).toBe(`${JOB_DIR}/roi_overlay.msh`);
    expect(params.get("open")).toBe("1");
  });

  it("leaves `open` off a link that did not ask for it", async () => {
    const { viewerSearch } = await import("../../src/renderer/app/openInViewer");
    expect(new URLSearchParams(viewerSearch({ subject: "ernie", kind: "subject" })).get("open")).toBeNull();
  });
});
