/**
 * The Viewer and the server agree on which subject owns a path, outside SimNIBS too.
 *
 * What it pins: after a change of subject the Viewer drops the rows of the "what will open" list
 * that belong to another subject (`pages/viewer/lib.ts::rescopeToSubject`). Before 2026-10-22 it
 * recognised a subject only under `derivatives/SimNIBS/sub-<id>/`, so ernie's FastSurfer or
 * FreeSurfer atlas — which the anatomy tree offers — stayed in the list after switching to 101,
 * and Open composed ernie's labels over 101's field.
 *
 * Where the numbers come from: `tests/fixtures/subject_paths.json`, a hand-written table of
 * container paths and owners derived from the BIDS layout rule in its `_about`. The same table
 * drives `tests/test_viewer_subject_ownership.py` against the server's refusal, so the client and
 * the server cannot disagree about a row without one side going red. 2026-10-22.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { rescopeToSubject, subjectOfPath } from "../../src/renderer/pages/viewer/lib";

interface Row {
  why: string;
  path: string;
  owner: string | null;
}
interface Table {
  rows: Row[];
  two_subject_scene: { files: string[]; subject: string; kept: string[]; dropped: string[] };
}

const table = JSON.parse(readFileSync(resolve(__dirname, "../../../tests/fixtures/subject_paths.json"), "utf8")) as Table;

describe("subjectOfPath over the shared ownership table", () => {
  it("has rows owned by a subject and rows owned by nobody", () => {
    expect(table.rows.length).toBeGreaterThanOrEqual(15);
    expect(table.rows.some((row) => row.owner === null)).toBe(true);
    expect(new Set(table.rows.map((row) => row.owner).filter((o) => o !== null)).size).toBeGreaterThanOrEqual(5);
  });

  it.each(table.rows.map((row) => [row.why, row] as const))("%s", (_why, row) => {
    expect(subjectOfPath(row.path)).toBe(row.owner);
  });
});

describe("rescopeToSubject with files outside SimNIBS", () => {
  it("drops another subject's FastSurfer atlas after a change of subject", () => {
    const scene = table.two_subject_scene;
    expect(rescopeToSubject(scene.files, scene.subject)).toEqual({ kept: scene.kept, dropped: scene.dropped });
  });

  it("keeps each row owned by the subject or by nobody, and drops every other, in order", () => {
    const paths = table.rows.map((row) => row.path);
    const { kept, dropped } = rescopeToSubject(paths, "101");
    expect(kept).toEqual(table.rows.filter((row) => row.owner === "101" || row.owner === null).map((row) => row.path));
    expect(dropped).toEqual(table.rows.filter((row) => row.owner !== "101" && row.owner !== null).map((row) => row.path));
    // The prefix neighbour is a different person.
    expect(dropped).toContain("/mnt/p/derivatives/SimNIBS/sub-1010/m2m_1010/T1.nii.gz");
  });
});
