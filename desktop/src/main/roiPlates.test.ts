import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { buildJob, PLATE_LIMIT, pngFor, renderPlatesForJob, roiScenes, sceneHasMesh, summariseResult } from "./roiPlates";

const SCENE = "/mnt/project/derivatives/SimNIBS/sub-101/flex-search/run/roi.tetravox.json";
const HOST_SCENE = "/Users/x/project/derivatives/SimNIBS/sub-101/flex-search/run/roi.tetravox.json";
const HOST_DIR = "/Users/x/project/derivatives/SimNIBS/sub-101/flex-search/run";

function hostOf(containerPath: string): string {
  return containerPath.replace("/mnt/project", "/Users/x/project");
}

const VOLUME_SCENE_TEXT = JSON.stringify({ version: 2, datasets: [{ id: "ds0", kind: "volume" }] });
const MESH_SCENE_TEXT = JSON.stringify({ version: 2, datasets: [{ id: "ds0", kind: "mesh" }] });
const RESULT_TEXT = JSON.stringify({
  ok: true,
  outputs: [{ action: 0, type: "screenshot", files: ["roi.png"], ms: 122 }],
  timings: { totalMs: 4776 },
  warnings: [],
  errors: [],
});

function deps(overrides: Partial<Parameters<typeof renderPlatesForJob>[1]> = {}) {
  const written = new Map<string, string>();
  const removed: string[] = [];
  const ran: { executable: string; args: string[]; home: string; homeExisted: boolean }[] = [];
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
      readFileText: async (path: string) => {
        if (path === HOST_SCENE) return VOLUME_SCENE_TEXT;
        if (path.endsWith("/job-result.json")) return RESULT_TEXT;
        throw new Error(`ENOENT: ${path}`);
      },
      removeFile: async (path: string) => void removed.push(path),
      run: async (executable: string, args: string[], home: string) => {
        ran.push({ executable, args, home, homeExisted: existsSync(home) });
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
    expect(pngFor("/a/Analyses/Mesh/run/scene.tetravox.json")).toBe("scene.png");
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

  it("adds the 3D pane only when the scene has a mesh or surface to draw in it", () => {
    const panelsOf = (text: string | undefined) =>
      (buildJob(HOST_SCENE, text) as { actions: { figure: { panels: string[]; columns: number } }[] }).actions[0]!
        .figure;
    expect(panelsOf(VOLUME_SCENE_TEXT)).toMatchObject({ panels: ["axial", "coronal", "sagittal"], columns: 3 });
    expect(panelsOf(MESH_SCENE_TEXT)).toMatchObject({
      panels: ["view3d", "axial", "coronal", "sagittal"],
      columns: 2,
    });
    expect(panelsOf(undefined).panels).toHaveLength(3);
    expect(sceneHasMesh("not json")).toBe(false);
    expect(sceneHasMesh(JSON.stringify({ datasets: [{ kind: "surface" }] }))).toBe(true);
  });
});

describe("summariseResult", () => {
  it("turns Tetravox's trace into one log line", () => {
    expect(summariseResult(RESULT_TEXT)).toBe("ok; roi.png; 4776 ms");
    expect(summariseResult(JSON.stringify({ ok: false, errors: ["boom"] }))).toBe(
      'failed; no file; ? ms; 1 error(s): ["boom"]',
    );
    expect(summariseResult("{")).toBeNull();
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
    // Never Electron's default TetraVox profile, which a user's own TetraVox shares.
    const profile = d.ran[0]!.args.find((arg) => arg.startsWith("--user-data-dir="))!.slice("--user-data-dir=".length);
    expect(profile).toContain("tit-tetravox-plate-");
    // Nor the user's ~/.tetravox (rc file, extensions): its TETRAVOX_HOME is inside the throwaway
    // profile, exists while it runs, and goes with it.
    expect(d.ran[0]!.home).toBe(join(profile, "tetravox-home"));
    expect(d.ran[0]!.homeExisted).toBe(true);
    expect(existsSync(profile)).toBe(false);
    const [, jobPath, , outDir] = d.ran[0]!.args;
    expect(outDir).toBe(HOST_DIR);
    expect(JSON.parse(d.written.get(jobPath!)!).scene).toEqual({ path: HOST_SCENE });
    // The document is derived from the scene in one line and is never left behind, and neither
    // is Tetravox's own trace: it is logged and removed.
    expect(d.removed).toEqual([jobPath, `${HOST_DIR}/job-result.json`]);
    expect(d.logged.join("\n")).toContain("roi.tetravox.json -> ok; roi.png; 4776 ms");
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
    expect(d.removed).toHaveLength(2);
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
