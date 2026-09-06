/**
 * Synthetic scene geometry — the fixture the renderer is exercised on when there is no server, no
 * container and no head model (lane SCB).
 *
 * It is an ellipsoid grid rather than a decimated real head for one reason: **every number about it
 * is derivable in closed form**. The vertex count is `(U+1)(V+1)`, the triangle count is `2UV`, the
 * bounding box is exactly the radii, the vertex at `(i = V/2, j = 0)` is exactly `(rx, 0, 0)`, and
 * the outward normal at any vertex is the gradient of the ellipsoid there. A test can therefore
 * assert what the parser and the normal computation produced against arithmetic instead of against
 * a recorded blob — which is the difference between a regression net and a test.
 *
 * The same module feeds two consumers, deliberately:
 *   - `scripts/make-scene-fixtures.ts`, which writes `desktop/tests/fixtures/scene/*.tvsc` (the
 *     files lane SCA's Python side reads to prove both implementations agree on §2.3);
 *   - `dev/SceneGallery.tsx`, which builds the same bytes in the browser and pushes them through
 *     the real `parseTvsc1`, so the gallery exercises the wire format rather than a shortcut past it.
 */

export interface Grid {
  positions: Float32Array;
  indices: Uint32Array;
  labels: Uint16Array;
}

export interface EllipsoidSpec {
  /** Semi-axes in mm: x right, y anterior, z superior. */
  radii: [number, number, number];
  /** Segments around the axial circle (phi). */
  u: number;
  /** Segments from vertex to base (theta). Keep even, so the equator is sampled exactly. */
  v: number;
  /** Region bands along theta and phi; label = 1 + band(theta) * phiBands + band(phi). */
  thetaBands?: number;
  phiBands?: number;
}

/** The two surfaces the fixtures ship, at the size a unit test can enumerate by hand. */
export const FIXTURE_SKIN: EllipsoidSpec = { radii: [78, 98, 88], u: 64, v: 32 };
export const FIXTURE_GM: EllipsoidSpec = { radii: [64, 82, 70], u: 64, v: 32, thetaBands: 4, phiBands: 8 };

/**
 * A UV-parametrised ellipsoid.
 *
 * ```
 * theta = pi * i / v          i = 0..v   (0 at +Z, pi at -Z)
 * phi   = 2pi * j / u         j = 0..u
 * p     = (rx sin(theta) cos(phi),  ry sin(theta) sin(phi),  rz cos(theta))
 * ```
 *
 * Winding is `(i,j) -> (i+1,j) -> (i,j+1)`, whose first two edges are the +theta and +phi tangents;
 * their cross product points outwards, which is what `gl.frontFace(CCW)` and `computeVertexNormals`
 * both assume. The two rings of triangles at the poles are degenerate (zero area, coincident
 * vertices) and contribute nothing to a normal — kept so that `2UV` is the triangle count with no
 * special case.
 */
export function ellipsoidGrid(spec: EllipsoidSpec): Grid {
  const { radii, u, v } = spec;
  const thetaBands = spec.thetaBands ?? 0;
  const phiBands = spec.phiBands ?? 0;
  const cols = u + 1;
  const rows = v + 1;
  const vertexCount = cols * rows;
  const positions = new Float32Array(vertexCount * 3);
  const labels = new Uint16Array(vertexCount);
  for (let i = 0; i < rows; i += 1) {
    const theta = (Math.PI * i) / v;
    const st = Math.sin(theta);
    const ct = Math.cos(theta);
    const tBand = thetaBands > 0 ? Math.min(thetaBands - 1, Math.floor((i * thetaBands) / rows)) : 0;
    for (let j = 0; j < cols; j += 1) {
      const phi = (2 * Math.PI * j) / u;
      const index = i * cols + j;
      positions[index * 3] = radii[0] * st * Math.cos(phi);
      positions[index * 3 + 1] = radii[1] * st * Math.sin(phi);
      positions[index * 3 + 2] = radii[2] * ct;
      if (phiBands > 0) {
        const pBand = Math.min(phiBands - 1, Math.floor((j * phiBands) / cols));
        labels[index] = 1 + tBand * phiBands + pBand;
      }
    }
  }
  const indices = new Uint32Array(u * v * 6);
  let k = 0;
  for (let i = 0; i < v; i += 1) {
    for (let j = 0; j < u; j += 1) {
      const a = i * cols + j;
      const b = a + 1;
      const c = a + cols;
      const d = c + 1;
      indices[k] = a;
      indices[k + 1] = c;
      indices[k + 2] = b;
      indices[k + 3] = b;
      indices[k + 4] = c;
      indices[k + 5] = d;
      k += 6;
    }
  }
  return { positions, indices, labels };
}

export interface FixtureMarker {
  id: string;
  label: string;
  world: [number, number, number];
}

/**
 * Markers on the skin ellipsoid at deterministic angles — a stand-in for an EEG net. Ring `r` sits
 * at `theta = pi * (r + 1) / (rings + 1)`, and the markers on it are evenly spaced in phi, pushed
 * 2 mm outwards so they sit ON the surface rather than in it (a marker exactly on the shell
 * z-fights with it and half of it disappears).
 */
export function fixtureMarkers(spec: EllipsoidSpec, rings = 3, perRing = 12): FixtureMarker[] {
  const markers: FixtureMarker[] = [];
  for (let r = 0; r < rings; r += 1) {
    const theta = (Math.PI * (r + 1)) / (rings + 1);
    for (let m = 0; m < perRing; m += 1) {
      const phi = (2 * Math.PI * m) / perRing;
      const scale = 1.03;
      markers.push({
        id: `E${r}-${m}`,
        label: `E${r}-${m}`,
        world: [
          spec.radii[0] * scale * Math.sin(theta) * Math.cos(phi),
          spec.radii[1] * scale * Math.sin(theta) * Math.sin(phi),
          spec.radii[2] * scale * Math.cos(theta),
        ],
      });
    }
  }
  return markers;
}

/** The grid resolution that lands on the plan's 150 k-triangle budget for one surface (S3):
 *  `2 * 400 * 190 = 152 000` triangles from 76 591 vertices. Used for the fps measurement. */
export const FIXTURE_BUDGET: EllipsoidSpec = { radii: [78, 98, 88], u: 400, v: 190 };

/**
 * The folded-winding fixture: two nested translucent sheets whose inner one is NOT consistently
 * wound, which is the case the `.annot`-labelled grey matter really is and the one the old
 * back-face/front-face split got wrong.
 *
 * Unlabelled on purpose. The invariant the pixel test asserts is *"a scanline across the inner
 * sheet has no colour discontinuity"*, and a banded surface has real colour steps at every band
 * boundary, which would make the assertion untestable. With no bands the only variation across the
 * sheet is the shading gradient, so any step in the scanline is a compositing defect and nothing
 * else.
 */
export const FIXTURE_FOLDED: EllipsoidSpec = { radii: [64, 82, 70], u: 64, v: 32 };

/** The second shell of the folded fixture, inside the first: the extra pair of sheets a camera ray
 *  crosses. Together they make four crossings per pixel over most of the silhouette, which is the
 *  median a real gyrified grey matter presents (Tetravox ARCHITECTURE §7.2 measures 4-6). */
export const FIXTURE_FOLDED_INNER: EllipsoidSpec = { radii: [42, 54, 46], u: 64, v: 32 };

/**
 * The folded-winding fixture: **one surface, four sheets, mixed winding** — the case the old
 * back-face/front-face split composited in the wrong order, and the reason the maintainer's
 * Optimizer pane showed shards of cortex through the scalp.
 *
 * Two concentric ellipsoids are concatenated into a single part, so a camera ray through the middle
 * of the frame crosses that one surface four times. That is what a real grey matter is: SimNIBS'
 * `gm` tag is one buffer holding both hemispheres, folded, and `orient_surface` marks it open — a
 * ray down a sulcus crosses it four to six times. `foldInnerHalf` then reverses the winding of
 * every triangle on the `x < 0` half, which is the other half of the truth: a folded surface has no
 * globally consistent "front face", so a renderer that decides which sheet to show from
 * `gl_FrontFacing` composites the two halves in different orders.
 *
 * Neither shell carries region bands. The invariant the pixel test asserts is *"a scanline across
 * the sheet has no colour discontinuity"*, and a banded surface has real colour steps at every band
 * boundary; with no bands the only variation is the shading gradient of two smooth ellipsoids, so
 * any step in the scanline is a compositing defect and nothing else.
 */
export function foldedFixtureGrid(): Grid {
  return foldInnerHalf(concatGrids(ellipsoidGrid(FIXTURE_FOLDED), ellipsoidGrid(FIXTURE_FOLDED_INNER)));
}

/** Two grids as one buffer, with the second's indices rebased. */
export function concatGrids(a: Grid, b: Grid): Grid {
  const positions = new Float32Array(a.positions.length + b.positions.length);
  positions.set(a.positions);
  positions.set(b.positions, a.positions.length);
  const offset = a.positions.length / 3;
  const indices = new Uint32Array(a.indices.length + b.indices.length);
  indices.set(a.indices);
  for (let i = 0; i < b.indices.length; i += 1) indices[a.indices.length + i] = (b.indices[i] as number) + offset;
  const labels = new Uint16Array(positions.length / 3);
  labels.set(a.labels);
  labels.set(b.labels, offset);
  return { positions, indices, labels };
}

/**
 * Reverses the winding of every triangle whose centroid is on the `x < 0` half.
 *
 * The result is a surface with a vertical seam down the middle: to the right of it the triangles
 * face outward, to the left they face inward. `cullFace(FRONT)` therefore keeps different sheets on
 * the two halves, so a renderer that reads the winding composites them in different orders and
 * leaves a step at the seam — the artefact this fixture exists to catch. A renderer that resolves
 * the sheet by depth (`glScene.ts` §"Resolving sheets") is indifferent to the flip.
 *
 * Lighting is unaffected: the fragment shader flips the normal for a back-facing fragment, so a
 * flipped triangle is shaded exactly as its unflipped twin would be.
 */
export function foldInnerHalf(grid: Grid): Grid {
  const { positions, indices } = grid;
  const out = Uint32Array.from(indices);
  for (let t = 0; t < out.length; t += 3) {
    const a = out[t] as number;
    const b = out[t + 1] as number;
    const c = out[t + 2] as number;
    const cx = ((positions[a * 3] as number) + (positions[b * 3] as number) + (positions[c * 3] as number)) / 3;
    if (cx < 0) {
      out[t + 1] = c;
      out[t + 2] = b;
    }
  }
  return { positions: grid.positions, indices: out, labels: grid.labels };
}
/**
 * A legend for the banded grey-matter fixture, in the shape `GET /api/scene/regions` returns:
 * `label` is the `uint16` in the payload and `color` is the region's own `"#rrggbb"`.
 *
 * The colours are a deterministic hue sweep rather than a real `.annot` colour table — the point is
 * that every band has a *different* colour and that a test can compute which one, which is what
 * makes "the selected region is painted in its own atlas colour" an arithmetic assertion.
 */
export function fixtureLegend(spec: EllipsoidSpec = FIXTURE_GM): { label: number; id: number; hemi: "lh" | "rh"; name: string; color: string }[] {
  const bands = (spec.thetaBands ?? 0) * (spec.phiBands ?? 0);
  const rows = [];
  for (let i = 0; i < bands; i += 1) {
    const hue = (i * 360) / Math.max(1, bands);
    rows.push({
      label: i + 1,
      id: i + 1,
      hemi: (i % 2 === 0 ? "lh" : "rh") as "lh" | "rh",
      name: `band-${i + 1}`,
      color: hslHex(hue, 0.62, 0.45),
    });
  }
  return rows;
}

/** HSL -> `"#rrggbb"`, so `fixtureLegend`'s colours are one line of arithmetic a test can repeat. */
export function hslHex(h: number, s: number, l: number): string {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  const [r1, g1, b1] =
    hp < 1 ? [c, x, 0] : hp < 2 ? [x, c, 0] : hp < 3 ? [0, c, x] : hp < 4 ? [0, x, c] : hp < 5 ? [x, 0, c] : [c, 0, x];
  const m = l - c / 2;
  const hex = (v: number): string =>
    Math.round(Math.min(255, Math.max(0, (v + m) * 255)))
      .toString(16)
      .padStart(2, "0");
  return `#${hex(r1)}${hex(g1)}${hex(b1)}`;
}
