/**
 * Saved-scene info card and thumbnail (2026-09-23). Values are authored rows, not server output.
 * Pins: Modified/Datasets appear only when they differ from Saved/Layers, and the thumbnail URL
 * changes with the scene's mtime so a re-saved scene's new preview is fetched, not the cached one.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/renderer/ui/Overlay", () => ({ Popover: ({ children }: { children: React.ReactNode }) => <>{children}</> }));

import { SceneInfo, ScenePreview } from "../../src/renderer/pages/viewer/SceneDetails";
import type { SavedScene } from "../../src/renderer/pages/viewer/api";

const base: SavedScene = { name: "s", slug: "s", path: "/p/code/ti-toolbox/viewer/scenes/s.tetravox.json", bytes: 10, saved_at: "2026-09-20T01:02:03+00:00", modified_at: "2026-09-20T01:02:03+00:00", layer_count: 3, dataset_count: 3, has_thumbnail: true };
const terms = (row: SavedScene) => [...renderToStaticMarkup(<SceneInfo row={row} />).matchAll(/<dt>([^<]+)<\/dt>/g)].map((m) => m[1]);

describe("saved scene details", () => {
  it("shows one row each when Modified equals Saved and Datasets equals Layers", () => {
    expect(terms(base)).toEqual(["Saved", "Layers", "Scene file", "Files"]);
  });
  it("shows Modified and Datasets when they carry different values", () => {
    expect(terms({ ...base, modified_at: "2026-09-21T00:00:00+00:00", dataset_count: 2 })).toEqual(["Saved", "Modified", "Layers", "Datasets", "Scene file", "Files"]);
  });
  it("versions the thumbnail URL by the scene's modification time", () => {
    const src = (row: SavedScene) => /src="([^"]+)"/.exec(renderToStaticMarkup(<ScenePreview row={row} active={false} revision={0} refresh={() => undefined} />))![1];
    expect(src(base)).toContain("/p/code/ti-toolbox/viewer/scenes/s.png?v=");
    expect(src(base)).not.toBe(src({ ...base, modified_at: "2026-09-21T00:00:00+00:00" }));
  });
});
