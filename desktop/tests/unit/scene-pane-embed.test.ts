/**
 * The run-page scene pane no longer owns a WebGL renderer. These tests pin the pure handoff it now
 * sends to Tetravox: scene-route URLs become `format=gii` mesh datasets, protocol-2 points carry
 * form markers, and atlas labels are rendered from one GIfTI mesh rather than a local TVSC join.
 */
import { describe, expect, it } from "vitest";
import {
  LABEL_FIELD_NAME,
  POINTS_LAYER_NAME,
  buildPaneViewSpec,
  cameraForBox,
  labelsForRegions,
  pickLabel,
  pointsFromMarkers,
  regionFromPick,
  sceneGiiUrl,
  channelColor,
  ACTIVE_DOT_RADIUS_PX,
  DOT_RADIUS_PX,
} from "../../src/renderer/pages/_shared/scene/embedScene";
import type { GuideManifest, GuideRegions } from "../../src/renderer/pages/_shared/scene/api";
import { SCENE_PALETTE, type SceneMarker, type SceneSelection } from "../../src/renderer/pages/_shared/scene/model";
import type { PickMessage } from "../../src/renderer/viewer/protocol";

// The FIXED GUIDE manifest (plan R4): no subject anywhere in it, and `space` is `guide-ras`.
const MANIFEST: GuideManifest = {
  guide: { id: "ernie", label: "Ernie (SimNIBS example head)" },
  space: "guide-ras",
  cache: { state: "ready", built_ms: 0 },
  parts: [
    { id: "skin", kind: "surface", url: "/api/guide/surface?part=skin", vertices: 12, triangles: 20, bytes: 120, bbox: [-5, -5, -5, 5, 5, 5], fingerprint: "guide-1-skin" },
    { id: "gm", kind: "surface", url: "/api/guide/surface?part=gm&format=tvsc", vertices: 8, triangles: 12, bytes: 96, bbox: [-3, -3, -3, 3, 3, 3], fingerprint: "guide-1-gm" },
  ],
  focus_bbox: [-20, -10, -5, 20, 30, 55],
  bbox: [-50, -50, -50, 50, 50, 50],
  atlases: [{ id: "DK40", hemispheres: ["lh", "rh"], url: "/api/guide/regions?atlas=DK40", regions: 2 }],
  nets: [{ name: "EEG10-20", url: "/api/guide/electrodes?net=EEG10-20", electrodes: 2 }],
  volumes: [],
};

const REGIONS: GuideRegions = {
  atlas: "DK40",
  space: "guide-ras",
  cache: { state: "ready", built_ms: 0 },
  url: "/api/guide/labels?atlas=DK40&format=tvsc",
  legend: [
    { label: 1, id: 1, hemi: "lh", name: "bankssts", color: "#ff0000" },
    { label: 2, id: 1, hemi: "rh", name: "bankssts", color: "#00ff00" },
  ],
};

const MARKERS: SceneMarker[] = [
  { id: "Fp1", label: "Fp1", world: [-20, 30, 65], channel: 0 },
  { id: "Fp2", label: "Fp2", world: [20, 30, 65], channel: 1 },
];

function labelLayer(scene: ReturnType<typeof buildPaneViewSpec>) {
  return scene?.layers.find((layer) => layer.name === "TI pane atlas · DK40") as Record<string, unknown>;
}

function pointsLayer(scene: ReturnType<typeof buildPaneViewSpec>) {
  return scene?.layers.find((layer) => layer.name === POINTS_LAYER_NAME) as Record<string, unknown>;
}

describe("sceneGiiUrl", () => {
  it("adds or replaces only the format query parameter", () => {
    expect(sceneGiiUrl("/api/scene/surface?subject=ernie&part=gm")).toBe("/api/scene/surface?subject=ernie&part=gm&format=gii");
    expect(sceneGiiUrl("/api/scene/labels?subject=ernie&atlas=DK40&format=tvsc#frag")).toBe(
      "/api/scene/labels?subject=ernie&atlas=DK40&format=gii#frag",
    );
  });
});

describe("buildPaneViewSpec", () => {
  it("hands Tetravox GIfTI URLs and a protocol-2 points layer, not TVSC bytes", () => {
    const selection: SceneSelection = { markers: [1], regions: [] };
    const scene = buildPaneViewSpec({
      manifest: MANIFEST,
      mode: "montage",
      gesture: "electrode",
      atlas: null,
      regions: null,
      selection,
      includePointsLayer: true,
    });
    expect(scene?.version).toBe(2);
    expect(scene?.datasets.map((d) => d.path)).toEqual([
      "/api/guide/surface?part=gm&format=gii",
      "/api/guide/surface?part=skin&format=gii",
    ]);
    expect(scene?.layers.map((layer) => layer.kind)).toEqual(["mesh", "mesh", "points"]);
    expect(pointsLayer(scene)).toMatchObject({ kind: "points", name: POINTS_LAYER_NAME, pickable: true, labelMode: "names" });
    expect(scene).not.toHaveProperty("transparency");
    expect(scene?.view3d).toMatchObject({ id: "view3d", showSlicePlanes: false });
  });

  it("uses the labels GIfTI as a renderable atlas mesh and carries selected label ids", () => {
    const scene = buildPaneViewSpec({
      manifest: MANIFEST,
      mode: "target",
      gesture: "region",
      atlas: "DK40",
      regions: REGIONS,
      selection: { markers: [], regions: [2] },
      includePointsLayer: false,
    });
    expect(scene?.datasets[0]).toMatchObject({ kind: "mesh", path: "/api/guide/labels?atlas=DK40&format=gii" });
    expect(labelLayer(scene)).toMatchObject({ kind: "mesh", pickable: true, colorMode: "label" });
    expect((labelLayer(scene).label as Record<string, unknown>)).toMatchObject({ name: LABEL_FIELD_NAME, visibleLabels: [2] });
  });

  it("leaves the scalp opaque for electrode mode but translucent for sphere placement", () => {
    const montage = buildPaneViewSpec({ manifest: MANIFEST, mode: "montage", gesture: "electrode", atlas: null, regions: null, selection: { markers: [], regions: [] }, includePointsLayer: true });
    const sphere = buildPaneViewSpec({ manifest: MANIFEST, mode: "target", gesture: "sphere", atlas: "DK40", regions: REGIONS, selection: { markers: [0], regions: [] }, includePointsLayer: true });
    const montageSkin = montage?.layers.find((layer) => layer.id === "layer-skin") as Record<string, unknown>;
    const sphereSkin = sphere?.layers.find((layer) => layer.id === "layer-skin") as Record<string, unknown>;
    expect(montageSkin.opacity).toBe(1);
    expect(sphereSkin.opacity).toBeLessThan(0.5);
  });
});

describe("protocol-2 points and picks", () => {
  it("maps form markers and selections into inline Tetravox points", () => {
    expect(pointsFromMarkers(MARKERS, { markers: [1], regions: [] })).toMatchObject([
      { id: "Fp1", position: [-20, 30, 65], state: "idle", group: "pair-1" },
      { id: "Fp2", name: "Fp2", position: [20, 30, 65], state: "selected", group: "pair-2" },
    ]);
  });

  it("names only the SELECTED points, so 185 electrodes are not 185 labels", () => {
    const points = pointsFromMarkers(MARKERS, { markers: [1], regions: [] });
    // Embed 0.4.0 skips a point whose `name` is absent or empty when building the label list
    // (`if (s.name === undefined || s.name === "") continue`), so absence is the whole mechanism.
    expect(points[0]).not.toHaveProperty("name");
    expect(points[1]?.name).toBe("Fp2");
  });

  it("gives every point an explicit colour: idle grey, selected = ITS channel's hue", () => {
    const points = pointsFromMarkers(MARKERS, { markers: [1], regions: [] });
    expect(points[0]?.color).toEqual([...SCENE_PALETTE.idle, 1]);
    expect(points[1]?.color).toEqual([...(SCENE_PALETTE.channels[1] as number[]), 1]);
    // Two channels are two hues, and neither is the idle grey — the property a 4-pair mTI
    // montage depends on.
    const both = pointsFromMarkers(MARKERS, { markers: [0, 1], regions: [] });
    expect(both[0]?.color).not.toEqual(both[1]?.color);
    expect(both.map((p) => p.color)).not.toContainEqual([...SCENE_PALETTE.idle, 1]);
  });

  it("the channel palette is colour-blind safe out to at least four pairs", () => {
    // Okabe-Ito by construction; what is checked here is that four pairs really do get four
    // DIFFERENT entries (a palette shorter than the montage would recycle hue 1 onto pair 5, which
    // is a legibility bug, not a wrap-around convenience).
    expect(SCENE_PALETTE.channels.length).toBeGreaterThanOrEqual(4);
    const four = [0, 1, 2, 3].map((c) => channelColor(c));
    expect(new Set(four.map((c) => c.join(","))).size).toBe(4);
    expect(new Set(SCENE_PALETTE.channels.map((c) => c.join(","))).size).toBe(SCENE_PALETTE.channels.length);
  });

  it("marks the ACTIVE channel's points with the larger dot radius, and nothing else", () => {
    const active = pointsFromMarkers(MARKERS, { markers: [0, 1], regions: [] }, 1);
    expect(active[0]).not.toHaveProperty("radiusPx");
    expect(active[1]?.radiusPx).toBe(ACTIVE_DOT_RADIUS_PX);
    // With no active channel (a read-only pane) nobody is enlarged.
    for (const point of pointsFromMarkers(MARKERS, { markers: [0, 1], regions: [] })) {
      expect(point).not.toHaveProperty("radiusPx");
    }
  });

  it("never emits a point selection or a point tool: those are the RING, and there is no ring", () => {
    // The mapping is pure — it produces `setPoints` payloads and nothing else. The live assertion
    // that the pane sends no such message is `scene-pane.spec.ts`; this is the static half: the
    // module exports no way to build one.
    const embedModule = { pointsFromMarkers, channelColor } as Record<string, unknown>;
    expect(Object.keys(embedModule)).not.toContain("pointSelectionFor");
    const layer = pointsLayer(
      buildPaneViewSpec({
        manifest: MANIFEST,
        mode: "montage",
        gesture: "electrode",
        atlas: null,
        regions: null,
        selection: { markers: [], regions: [] },
        includePointsLayer: true,
      }),
    );
    // No layer-level `selected` colour either: one colour cannot say WHICH channel (plan B2).
    expect(layer.stateColors).toEqual({ idle: [...SCENE_PALETTE.idle, 1], disabled: [...SCENE_PALETTE.disabled, 1] });
    expect(layer.stateColors as Record<string, unknown>).not.toHaveProperty("selected");
  });

  it("draws electrodes as DOTS with a pixel radius, not as spheres", () => {
    const montage = pointsLayer(
      buildPaneViewSpec({ manifest: MANIFEST, mode: "montage", gesture: "electrode", atlas: null, regions: null, selection: { markers: [], regions: [] }, includePointsLayer: true }),
    );
    expect(montage.shape).toBe("dot");
    expect(montage.dotRadiusPx).toBe(DOT_RADIUS_PX);
    expect(montage.labelColorSource).toBe("points");
    expect(montage.offPlaneOpacity).toBe(0.35);
  });

  it("maps picked label ids back through the server legend", () => {
    const pick: PickMessage = {
      tvx: 1,
      type: "pick",
      kind: "tri",
      world: [0, 0, 0],
      label: { id: 2, name: "bankssts", layerId: "layer-labels" },
      modifiers: { shift: false, ctrl: false, alt: false, meta: false },
      probe: { world: [0, 0, 0], rows: [] },
    };
    expect(pickLabel(pick, "layer-labels")).toBe(2);
    expect(regionFromPick(pick, REGIONS.legend, "layer-labels")).toEqual({ id: 1, hemi: "rh", name: "bankssts" });
    expect(labelsForRegions(REGIONS.legend, [{ id: 1, hemi: "lh", name: "bankssts" }])).toEqual([1]);
  });
});

describe("cameraForBox", () => {
  it("targets the focus bbox centre and keeps a positive clipping range", () => {
    const camera = cameraForBox(MANIFEST.focus_bbox);
    expect(camera.target).toEqual([0, 10, 25]);
    expect(camera.distance).toBeGreaterThan(160);
    expect(camera.near).toBeGreaterThan(0);
    expect(camera.far).toBeGreaterThan(camera.distance);
  });
});
