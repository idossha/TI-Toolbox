import type { Vec3 } from "../../../scene";
import type { SceneMarker } from "./model";

/** Join by selected cap name, never by the cap file's electrode order. Distances are Euclidean. */
export function capDisplacements(originals: { x: number; y: number; z: number }[], pairs: [string, string][], markers: SceneMarker[]) {
  const byName = new Map(markers.map((marker) => [marker.id, marker]));
  return pairs.flat().flatMap((name, index) => {
    const original = originals[index];
    const destination = byName.get(name);
    if (!original || !destination) return [];
    const from: Vec3 = [original.x, original.y, original.z];
    if (!from.every(Number.isFinite) || !destination.world.every(Number.isFinite)) return [];
    const distance = Math.hypot(...from.map((value, axis) => value - destination.world[axis]!));
    return [{ from, to: destination.world, label: `${name}: ${distance.toFixed(1)} mm` }];
  });
}
