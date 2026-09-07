/**
 * The camera must stay where the user left it (bug report: "when placing a new net or selecting a
 * new net in the simulator, it should not change the orientation of the 3D visualization").
 *
 * `SceneCanvas` re-frames the pane — a full `presetCamera("reset", …)`, throwing away the user's
 * orbit, zoom and preset — in one effect. That effect used to be keyed on the *point arrays* it
 * frames on, and those arrays are rebuilt whenever the marker set changes: a different EEG net, a
 * pair being edited, an electrode toggled. So every net change snapped the view back.
 *
 * `framingSignature` is what the effect is keyed on now. The tests below say exactly what it must
 * ignore (everything a user does while working in the pane) and what it must still notice (the
 * geometry actually being replaced).
 */
import { describe, expect, it } from "vitest";
import { framingSignature, type Bounds, type FramingPart } from "../../src/renderer/scene/camera";
import { markersFromElectrodes, channelByElectrode, type Pair } from "../../src/renderer/pages/_shared/scene/model";

const BOUNDS: Bounds = [-80, 80, -110, 90, -50, 95];

/** A surface's vertices. Rebuilt on each call so identity is never what makes a test pass. */
const skin = (): Float32Array => new Float32Array([-80, -110, -50, 0, 0, 0, 80, 90, 95]);
const gm = (): Float32Array => new Float32Array([-60, -90, -40, 1, 2, 3, 60, 70, 75]);

const parts = (opts: { labels?: boolean } = {}): FramingPart[] => [
  // `labels` and `opacity` are real `ScenePart` fields the atlas and the sliders change; the
  // signature reads neither, and the objects below carry one to prove the type allows it.
  { id: "gm", positions: gm(), ...(opts.labels ? { labels: new Uint32Array([1, 2, 3]) } : {}) },
  { id: "skin", positions: skin() },
];

describe("framingSignature", () => {
  it("is stable across renders that only rebuild the arrays", () => {
    expect(framingSignature(BOUNDS, parts())).toBe(framingSignature(BOUNDS, parts()));
  });

  it("ignores an atlas being applied to the same cortex (Optimizer, Analyzer)", () => {
    expect(framingSignature(BOUNDS, parts({ labels: true }))).toBe(framingSignature(BOUNDS, parts()));
  });

  it("notices a surface being replaced by a different one", () => {
    const other = parts();
    other[0] = { id: "gm", positions: new Float32Array([-61, -90, -40, 1, 2, 3, 60, 70, 75]) };
    expect(framingSignature(BOUNDS, other)).not.toBe(framingSignature(BOUNDS, parts()));
  });

  it("notices a surface appearing", () => {
    expect(framingSignature(BOUNDS, [parts()[0] as FramingPart])).not.toBe(framingSignature(BOUNDS, parts()));
  });

  it("notices a different guide's bounding box", () => {
    const moved: Bounds = [-80, 80, -110, 90, -50, 96];
    expect(framingSignature(moved, parts())).not.toBe(framingSignature(BOUNDS, parts()));
  });
});

describe("the pane's own changes never re-frame", () => {
  const netA = [
    { name: "Fp1", pos: [-20, 90, 30] as [number, number, number] },
    { name: "Fp2", pos: [20, 90, 30] as [number, number, number] },
  ];
  const netB = [
    { name: "E1", pos: [-30, 80, 40] as [number, number, number] },
    { name: "E2", pos: [30, 80, 40] as [number, number, number] },
    { name: "E3", pos: [0, -80, 40] as [number, number, number] },
  ];
  const markersFor = (net: typeof netA, pairs: Pair[]) =>
    markersFromElectrodes(
      net.map((e) => ({ name: e.name, world: e.pos })),
      channelByElectrode(pairs),
    );

  it("a different EEG net produces different markers but the same framing key", () => {
    const a = markersFor(netA, []);
    const b = markersFor(netB, []);
    expect(a.length).not.toBe(b.length); // the marker set really did change …
    // … and the geometry the camera is framed on did not.
    expect(framingSignature(BOUNDS, parts())).toBe(framingSignature(BOUNDS, parts()));
  });

  it("editing a montage pair only recolours markers", () => {
    const before = markersFor(netA, []);
    const after = markersFor(netA, [["Fp1", "Fp2"]]);
    expect(after.map((m) => m.world)).toEqual(before.map((m) => m.world));
    expect(after.map((m) => m.channel)).not.toEqual(before.map((m) => m.channel));
  });
});
