import { describe, expect, it, vi } from "vitest";
import { buildJob, PLATE_LIMIT, pngFor, renderPlatesForJob, roiScenes } from "./roiPlates";

const SCENE = "/mnt/project/derivatives/SimNIBS/sub-101/flex-search/run/roi.tetravox.json";
const HOST_SCENE = "/Users/x/project/derivatives/SimNIBS/sub-101/flex-search/run/roi.tetravox.json";
const HOST_DIR = "/Users/x/project/derivatives/SimNIBS/sub-101/flex-search/run";

function hostOf(containerPath: string): string {
  return containerPath.replace("/mnt/project", "/Users/x/project");
}

function deps(overrides: Partial<Parameters<typeof renderPlatesForJob>[1]> = {}) {
  const written = new Map<string, string>();
  const removed: string[] = [];
  const ran: { executable: string; args: string[] }[] = [];
  const logged: string[] = [];
  return {
    written,
    removed,
    ran,
    logged,
    value: {
      artifactPaths: async () => [SCENE, "/mnt/project/x/summary.csv"],
      toHostPath: async (path: string) => hostOf(path),
      viewerExecutable: async () => "/Applications/Tetravox.app/Contents/MacOS/Tetravox",
      writeFileText: async (path: string, text: string) => void written.set(path, text),
      removeFile: async (path: string) => void removed.push(path),
      run: async (executable: string, args: string[]) => {
        ran.push({ executable, args });
        return 0;
      },
      logLine: (_level: "info" | "warn", message: string) => void logged.push(message),
      ...overrides,
    },
  };
}

describe("roiScenes", () => {
  it("picks the scenes out of an artifact list, sorted and de-duplicated", () => {
    expect(roiScenes(["/a/b.png", SCENE, SCENE, "/a/c.json"])).toEqual([SCENE]);
  });

  it("caps how many scenes one job can queue", () => {
    const many = Array.from({ length: 20 }, (_, i) => `/a/roi_${i}.tetravox.json`);
    expect(roiScenes(many)).toHaveLength(PLATE_LIMIT);
  });
});

describe("pngFor", () => {
  it("names the picture after the scene it comes from", () => {
    expect(pngFor(SCENE)).toBe("roi.png");
    expect(pngFor("/a/roi_field.tetravox.json")).toBe("roi_field.png");
  });
});

describe("buildJob", () => {
  it("opens the saved scene and decides nothing about how the ROI looks", () => {
    const job = buildJob(HOST_SCENE) as {
      scene: { path: string; files?: string[] };
      actions: { type: string; out: string; view: string; figure: { panels: string[] } }[];
    };
    expect(job.scene).toEqual({ path: HOST_SCENE });
    expect(job.scene.files).toBeUndefined();
    expect(job.actions).toHaveLength(1);
    expect(job.actions[0]!.type).toBe("screenshot");
    // `out` is a bare name under `--out`; a leading slash or a `..` is refused by Tetravox.
    expect(job.actions[0]!.out).toBe("roi.png");
    expect(job.actions[0]!.view).toBe("figure");
    expect(job.actions[0]!.figure.panels).toEqual(["axial", "coronal", "sagittal"]);
  });
});

describe("renderPlatesForJob", () => {
  it("runs Tetravox offscreen on the scene, in the scene's own directory", async () => {
    const d = deps();
    const result = await renderPlatesForJob("job-1", d.value);

    expect(result.rendered).toEqual([SCENE]);
    expect(d.ran).toHaveLength(1);
    expect(d.ran[0]!.args[0]).toBe("--job");
    expect(d.ran[0]!.args).toContain("--quiet");
    const [, jobPath, , outDir] = d.ran[0]!.args;
    expect(outDir).toBe(HOST_DIR);
    expect(JSON.parse(d.written.get(jobPath!)!).scene).toEqual({ path: HOST_SCENE });
    // The document is derived from the scene in one line and is never left behind.
    expect(d.removed).toEqual([jobPath]);
  });

  it("does nothing at all when the job left no scene", async () => {
    const d = deps({ artifactPaths: async () => ["/mnt/project/x/summary.csv"] });
    const viewer = vi.fn();
    await renderPlatesForJob("job-1", { ...d.value, viewerExecutable: viewer as never });
    expect(viewer).not.toHaveBeenCalled();
  });

  it("leaves the scene alone and says so when there is no Tetravox", async () => {
    const d = deps({ viewerExecutable: async () => undefined });
    const result = await renderPlatesForJob("job-1", d.value);

    expect(result).toEqual({ rendered: [], skipped: [SCENE] });
    expect(d.ran).toHaveLength(0);
    expect(d.logged.join(" ")).toContain("no Tetravox");
  });

  it("keeps the scene and makes no picture when Tetravox fails", async () => {
    const d = deps({ run: async () => 1 });
    const result = await renderPlatesForJob("job-1", d.value);

    expect(result.rendered).toEqual([]);
    expect(result.skipped).toEqual([SCENE]);
    expect(d.logged.join(" ")).toContain("the scene stands");
  });

  it("never throws when the document cannot be written, and still cleans up", async () => {
    const d = deps({
      writeFileText: async () => {
        throw new Error("read-only");
      },
    });
    await expect(renderPlatesForJob("job-1", d.value)).resolves.toEqual({ rendered: [], skipped: [SCENE] });
    expect(d.removed).toHaveLength(1);
  });

  it("skips a scene outside the mounted project", async () => {
    const d = deps({ toHostPath: async () => null });
    await expect(renderPlatesForJob("job-1", d.value)).resolves.toEqual({ rendered: [], skipped: [SCENE] });
  });

  it("never throws when the job's artifacts cannot be listed", async () => {
    const d = deps({
      artifactPaths: async () => {
        throw new Error("offline");
      },
    });
    await expect(renderPlatesForJob("job-1", d.value)).resolves.toEqual({ rendered: [], skipped: [] });
  });
});
