/**
 * The scene renderer's gallery entry (lane SCB): `<SceneCanvas>` mounted on synthetic fixtures,
 * with no server, no container and no head model.
 *
 * It exists so the renderer can be exercised — and asserted on — offscreen. The geometry is built
 * in the browser, encoded to `TVSC1` and pushed back through the real `parseTvsc1`, so what the
 * gallery draws has been through the same wire format a `GET /api/scene/surface` response goes
 * through. A gallery that fed the arrays straight to the GPU would leave the parser untested on the
 * one path that matters.
 *
 * The canvas is mounted only after a click. A WebGL2 context, two programs and a 150 k-triangle
 * upload are not what the rest of the design gallery's screenshots should be paying for.
 */
import { useMemo, useState } from "react";
import { Button } from "../ui/Button";
import { SegmentedControl } from "../ui/SegmentedControl";
import { SceneCanvas } from "../scene/SceneCanvas";
import { SCENE_PALETTE } from "../scene/palette";
import { encodeTvsc1, parseTvsc1 } from "../scene/tvsc";
import type { SceneMode, SceneSelection } from "../scene/selection";
import type { ScenePart, SceneMarker } from "../scene/types";
import { buildLabelColors } from "../scene/glScene";
import {
  FIXTURE_BUDGET,
  FIXTURE_GM,
  FIXTURE_SKIN,
  ellipsoidGrid,
  fixtureLegend,
  fixtureMarkers,
  foldedFixtureGrid,
} from "./sceneFixtures";

/**
 * `folded` is the transparency fixture: the inner sheet with half its triangles wound inward, which
 * is what a real folded cortex looks like to a renderer and the case the old back-face/front-face
 * split composited in the wrong order (`glScene.ts` §"Resolving sheets").
 */
type FixtureSize = "small" | "budget" | "folded";

/** Builds a part the long way round: grid -> TVSC1 bytes -> parser -> arrays. */
function part(
  id: string,
  label: string,
  spec: Parameters<typeof ellipsoidGrid>[0],
  color: [number, number, number],
  opacity: number,
  withLabels: boolean,
  folded = false,
): ScenePart {
  const grid = folded ? foldedFixtureGrid() : ellipsoidGrid(spec);
  const buffer = encodeTvsc1({
    positions: grid.positions,
    indices: grid.indices,
    labels: withLabels ? grid.labels : null,
  });
  const parsed = parseTvsc1(buffer);
  return {
    id,
    label,
    positions: parsed.positions,
    indices: parsed.indices ?? new Uint32Array(),
    labels: parsed.labels,
    color,
    opacity,
  };
}

export function SceneGallery() {
  const [mounted, setMounted] = useState(false);
  const [mode, setMode] = useState<SceneMode>("montage");
  const [size, setSize] = useState<FixtureSize>("small");
  const [selection, setSelection] = useState<SceneSelection>({ markers: [], regions: [] });

  const parts = useMemo<ScenePart[]>(() => {
    if (!mounted) return [];
    return [
      size === "folded"
        ? part("gm", "Grey matter", FIXTURE_GM, SCENE_PALETTE.gm, 0.6, false, true)
        : part("gm", "Grey matter", FIXTURE_GM, SCENE_PALETTE.gm, 0.55, true),
      part("skin", "Skin", size === "budget" ? FIXTURE_BUDGET : FIXTURE_SKIN, SCENE_PALETTE.skin, 0.25, false),
    ];
  }, [mounted, size]);

  /** The fixture atlas' own colours, in the shape the real legend arrives in. */
  const labelColors = useMemo(() => buildLabelColors(fixtureLegend()), []);

  const markers = useMemo<SceneMarker[]>(() => {
    if (!mounted) return [];
    return fixtureMarkers(FIXTURE_SKIN).map((marker, index) => ({
      id: marker.id,
      label: marker.label,
      world: marker.world,
      // Two channels, so the per-channel marker colours are exercised as well as the selection one.
      channel: index % 12 === 0 ? 0 : index % 12 === 6 ? 1 : undefined,
    }));
  }, [mounted]);

  const triangles = parts.reduce((sum, p) => sum + p.indices.length / 3, 0);

  return (
    <section style={{ marginBottom: "var(--space-8)" }} data-testid="scene-gallery">
      <h2 className="text-section" style={{ marginBottom: "var(--space-3)" }}>
        Scene (3D pane)
      </h2>
      <p className="field-help" style={{ marginBottom: "var(--space-3)", maxWidth: "72ch" }}>
        The slim scene renderer on synthetic fixtures — an ellipsoid &ldquo;skin&rdquo; and a labelled
        &ldquo;grey matter&rdquo;, both round-tripped through TVSC1, with 36 markers. Drag to orbit,
        shift-drag to pan, wheel to zoom, click a marker or a region depending on the mode.
      </p>

      <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", marginBottom: "var(--space-3)", flexWrap: "wrap" }}>
        <Button size="sm" variant={mounted ? "secondary" : "primary"} onClick={() => setMounted((v) => !v)} data-testid="scene-mount">
          {mounted ? "Unmount scene" : "Mount scene"}
        </Button>
        <SegmentedControl
          aria-label="Scene mode"
          size="sm"
          value={mode}
          onValueChange={(value) => {
            setMode(value as SceneMode);
            setSelection({ markers: [], regions: [] });
          }}
          options={[
            { value: "montage", label: "montage" },
            { value: "target", label: "target" },
            { value: "inspect", label: "inspect" },
          ]}
        />
        <SegmentedControl
          aria-label="Fixture size"
          size="sm"
          value={size}
          onValueChange={(value) => setSize(value as FixtureSize)}
          options={[
            { value: "small", label: "4k tri", title: "64x32 grid per surface" },
            { value: "budget", label: "150k tri", title: "the plan's per-surface budget (S3)" },
            { value: "folded", label: "folded", title: "inner sheet half-wound inward — the transparency fixture" },
          ]}
        />
        <span className="field-help" data-testid="scene-gallery-triangles">
          {triangles.toLocaleString("en-US")} triangles
        </span>
      </div>

      {mounted && (
        <div style={{ height: 420, maxWidth: 880, border: "1px solid var(--line)", borderRadius: "var(--radius-card)", overflow: "hidden" }}>
          <SceneCanvas
            mode={mode}
            parts={parts}
            markers={markers}
            labelColors={labelColors}
            selection={selection}
            onSelectionChange={setSelection}
            label="Scene gallery fixture"
          />
        </div>
      )}

      <pre
        data-testid="scene-gallery-selection"
        className="field-help"
        style={{ marginTop: "var(--space-2)", fontFamily: "var(--font-mono)", fontSize: 11 }}
      >
        {JSON.stringify(selection)}
      </pre>
    </section>
  );
}
