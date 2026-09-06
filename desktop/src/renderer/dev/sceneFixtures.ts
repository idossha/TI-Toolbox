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
