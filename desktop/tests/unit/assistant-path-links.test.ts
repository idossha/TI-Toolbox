// @vitest-environment jsdom
/**
 * Which printed paths the Assistant terminal underlines (`pages/assistant/pathLinks.ts`,
 * ARCHITECTURE §5 `assistant.openPath`). Expected matches are written by hand from the rule in the
 * module header (absolute only inside the project folder; relative only `./`, `../` or a project
 * top-level folder); main re-validates every click (`src/main/assistant.test.ts`). The last test
 * runs a real, unopened xterm `Terminal` so the link columns are xterm's own cell positions,
 * wide characters included. 2026-10-08.
 */
import { describe, expect, it } from "vitest";
import { Terminal, type ILink } from "@xterm/xterm";
import { findPaths, pathLinkProvider } from "../../src/renderer/pages/assistant/pathLinks";

const ROOT = "/Users/u/proj";
const texts = (line: string, root: string | undefined = ROOT, windows = false) => findPaths(line, root, windows).map((m) => m.text);

describe("findPaths", () => {
  it("links absolute paths inside the project folder only", () => {
    expect(texts("wrote /Users/u/proj/derivatives/SimNIBS/sub-CHN/flex-search/run1/opt.json and /etc/hosts")).toEqual([
      "/Users/u/proj/derivatives/SimNIBS/sub-CHN/flex-search/run1/opt.json",
    ]);
    expect(texts("cwd=/Users/u/proj")).toEqual(["/Users/u/proj"]);
    // A sibling folder that merely shares the prefix is outside.
    expect(texts("/Users/u/project2/x")).toEqual([]);
    expect(findPaths("/Users/u/proj/x", undefined)).toEqual([]);
  });

  it("links paths relative to the project folder by their top-level folder or ./ ../", () => {
    expect(texts("Saved to derivatives/SimNIBS/sub-CHN/flex-search/insula. Next: sourcedata/sub-CHN/anat")).toEqual([
      "derivatives/SimNIBS/sub-CHN/flex-search/insula",
      "sourcedata/sub-CHN/anat",
    ]);
    expect(texts("(code/ti-toolbox/proposals/a.json) ./notes.md ../elsewhere sub-101/anat")).toEqual([
      "code/ti-toolbox/proposals/a.json",
      "./notes.md",
      "../elsewhere",
      "sub-101/anat",
    ]);
    // Arbitrary relative words and paths glued to other text are not links.
    expect(texts("lib/foo.ts myderivatives/x src/main")).toEqual([]);
  });

  it("never mistakes a URL, a bare slash or a line number suffix for a path", () => {
    expect(texts("see https://code.claude.com/docs/en/setup or / alone or ./")).toEqual([]);
    expect(texts("derivatives/a.py:12")).toEqual(["derivatives/a.py"]);
  });

  it("matches Windows project paths case-insensitively with either separator", () => {
    expect(texts("C:\\Users\\U\\Proj\\derivatives\\x.nii.gz D:\\other", "C:\\Users\\u\\proj", true)).toEqual(["C:\\Users\\U\\Proj\\derivatives\\x.nii.gz"]);
  });
});

describe("pathLinkProvider", () => {
  it("places each link on the cells xterm drew it in, after wide characters too", async () => {
    const term = new Terminal({ cols: 120, rows: 5, allowProposedApi: true });
    await new Promise<void>((done) => term.write("⏺ 日本 derivatives/a.json ok", done));
    const opened: string[] = [];
    const links = await new Promise<ILink[] | undefined>((done) => pathLinkProvider(term, () => ROOT, false, (p) => opened.push(p)).provideLinks(1, done));
    expect(links).toHaveLength(1);
    const link = links![0]!;
    expect(link.text).toBe("derivatives/a.json");
    // "⏺ " is 2 cells, "日本" is 4 (two wide characters) and the space 1: the path starts in column 8 (1-based).
    expect(link.range).toEqual({ start: { x: 8, y: 1 }, end: { x: 8 + "derivatives/a.json".length - 1, y: 1 } });
    link.activate(new MouseEvent("click"), link.text);
    expect(opened).toEqual(["derivatives/a.json"]);
    term.dispose();
  });
});
