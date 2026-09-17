import { describe, expect, it, vi } from "vitest";
import { jobDocumentFor, PLATE_LIMIT, plateRequests, renderPlatesForJob, toHostDocument } from "./roiPlates";

const REQUEST = "/mnt/project/derivatives/SimNIBS/sub-101/flex-search/run/roi_plate.plate-request.json";
const DOCUMENT = "/mnt/project/derivatives/SimNIBS/sub-101/flex-search/run/roi_plate.tetravox-job.json";

function hostOf(containerPath: string): string {
  return containerPath.replace("/mnt/project", "/Users/x/project");
}

function deps(overrides: Partial<Parameters<typeof renderPlatesForJob>[1]> = {}) {
  const written = new Map<string, string>();
  const ran: { executable: string; args: string[] }[] = [];
  const logged: string[] = [];
  return {
    written,
    ran,
    logged,
    value: {
      artifactPaths: async () => [REQUEST, "/mnt/project/x/summary.csv"],
      toHostPath: async (path: string) => hostOf(path),
      viewerExecutable: async () => "/Applications/Tetravox.app/Contents/MacOS/Tetravox",
      readFileText: async () =>
        JSON.stringify({ version: 1, scene: { files: ["/mnt/project/a/T1.nii.gz", "/mnt/project/a/roi.nii"] }, actions: [] }),
      writeFileText: async (path: string, text: string) => void written.set(path, text),
      run: async (executable: string, args: string[]) => {
        ran.push({ executable, args });
        return 0;
      },
      logLine: (_level: "info" | "warn", message: string) => void logged.push(message),
      ...overrides,
    },
  };
}

describe("plateRequests", () => {
  it("picks the requests out of an artifact list, sorted and de-duplicated", () => {
    expect(plateRequests(["/a/b.png", REQUEST, REQUEST, "/a/c.json"])).toEqual([REQUEST]);
  });

  it("caps how many plates one job can queue", () => {
    const many = Array.from({ length: 20 }, (_, i) => `/a/roi_${i}.plate-request.json`);
    expect(plateRequests(many)).toHaveLength(PLATE_LIMIT);
  });
});

describe("jobDocumentFor", () => {
  it("names the document the Python side wrote beside the request", () => {
    expect(jobDocumentFor(REQUEST)).toBe(DOCUMENT);
  });
});

describe("toHostDocument", () => {
  it("maps every dataset path into the host filesystem", async () => {
    const mapped = await toHostDocument({ scene: { files: ["/mnt/project/a.nii"] } }, async (p) => hostOf(p));
    expect(mapped?.scene?.files).toEqual(["/Users/x/project/a.nii"]);
  });

  it("refuses the whole document when one path does not map", async () => {
    // A plate missing a layer is worse than the matplotlib plate it would overwrite.
    const mapped = await toHostDocument(
      { scene: { files: ["/mnt/project/a.nii", "/elsewhere/b.nii"] } },
      async (p) => (p.startsWith("/mnt/project") ? hostOf(p) : null),
    );
    expect(mapped).toBeNull();
  });
});

describe("renderPlatesForJob", () => {
  it("runs Tetravox offscreen on the host-path document, in the plate's own directory", async () => {
    const d = deps();
    const result = await renderPlatesForJob("job-1", d.value);

    expect(result.rendered).toEqual([REQUEST]);
    expect(d.ran).toHaveLength(1);
    expect(d.ran[0]!.args[0]).toBe("--job");
    expect(d.ran[0]!.args).toContain("--quiet");
    const [, jobPath, , outDir] = d.ran[0]!.args;
    expect(jobPath).toBe("/Users/x/project/derivatives/SimNIBS/sub-101/flex-search/run/roi_plate.tetravox-job.host.json");
    expect(outDir).toBe("/Users/x/project/derivatives/SimNIBS/sub-101/flex-search/run");
    expect(JSON.parse(d.written.get(jobPath!)!).scene.files).toEqual([
      "/Users/x/project/a/T1.nii.gz",
      "/Users/x/project/a/roi.nii",
    ]);
  });

  it("does nothing at all when the job left no plate request", async () => {
    const d = deps({ artifactPaths: async () => ["/mnt/project/x/summary.csv"] });
    const viewer = vi.fn();
    await renderPlatesForJob("job-1", { ...d.value, viewerExecutable: viewer as never });
    expect(viewer).not.toHaveBeenCalled();
  });

  it("leaves the drawn plate alone and says so when there is no Tetravox", async () => {
    const d = deps({ viewerExecutable: async () => undefined });
    const result = await renderPlatesForJob("job-1", d.value);

    expect(result).toEqual({ rendered: [], skipped: [REQUEST] });
    expect(d.ran).toHaveLength(0);
    expect(d.logged.join(" ")).toContain("no Tetravox");
  });

  it("leaves the drawn plate alone when Tetravox fails", async () => {
    const d = deps({ run: async () => 1 });
    const result = await renderPlatesForJob("job-1", d.value);

    expect(result.rendered).toEqual([]);
    expect(result.skipped).toEqual([REQUEST]);
    expect(d.logged.join(" ")).toContain("the drawn plate stands");
  });

  it("never throws when the document is unreadable", async () => {
    const d = deps({
      readFileText: async () => {
        throw new Error("gone");
      },
    });
    await expect(renderPlatesForJob("job-1", d.value)).resolves.toEqual({ rendered: [], skipped: [REQUEST] });
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
