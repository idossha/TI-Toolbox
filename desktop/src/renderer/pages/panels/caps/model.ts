/** The EEG caps panel's pure core: status wording, warnings and scene markers. Unit-tested in
 *  `tests/unit/caps-panel.test.ts`. */
import type { SemanticKind } from "../../../ui/Status";
import { SCENE_CATEGORICAL } from "../../../scene/palette";
import type { SceneMarker } from "../../_shared/scene/model";
import type { CapInspection, CapStatus } from "./api";

export function capStatus(cap: CapStatus): { label: string; kind: SemanticKind; title?: string } {
  if (!cap.on_subject) return { label: "not on subject", kind: "neutral" };
  if (cap.source === null) return { label: "on subject", kind: "success", title: "No MNI source: it cannot be re-applied here." };
  if (cap.outdated) return { label: "outdated", kind: "warning", title: "The MNI cap is newer than this subject's copy — re-apply it." };
  return { label: "on subject", kind: "success" };
}

/** Caps the Apply button would overwrite, so the page can ask before sending `overwrite`. */
export function existingAmong(caps: CapStatus[], names: string[]): string[] {
  const on = new Set(caps.filter((c) => c.on_subject).map((c) => c.name));
  return names.filter((name) => on.has(name));
}

/** "Re-apply all": every cap with an MNI source that is already on the subject. */
export function reapplicable(caps: CapStatus[]): string[] {
  return caps.filter((c) => c.on_subject && c.source !== null).map((c) => c.name);
}

/** One sentence per problem the inspection found; empty when the net looks sound. */
export function inspectionWarnings(inspection: CapInspection): string[] {
  const out: string[] = [];
  const pairs = inspection.collapsed;
  if (pairs.length > 0) {
    const shown = pairs.slice(0, 3).map((p) => `${p.a}–${p.b} ${p.distance_mm.toFixed(1)} mm`).join(", ");
    out.push(`${pairs.length} electrode pair${pairs.length === 1 ? "" : "s"} closer than ${inspection.collapse_mm} mm: ${shown}${pairs.length > 3 ? ", …" : ""}`);
  }
  if (inspection.duplicate_names.length > 0) out.push(`Duplicate labels: ${inspection.duplicate_names.join(", ")}`);
  return out;
}

const NET_COLOR = SCENE_CATEGORICAL[0]!; // blue
const COMPARE_COLOR = SCENE_CATEGORICAL[1]!; // orange
const WARN_COLOR = SCENE_CATEGORICAL[7]!; // red

/** The net's electrodes (collapsed ones in red), then the compare net's. Index i < n is row i. */
export function inspectionMarkers(inspection: CapInspection): SceneMarker[] {
  const collapsed = new Set(inspection.collapsed.flatMap((p) => [p.a, p.b]));
  const net = inspection.electrodes.map((e, i) => ({
    id: `net:${i}`,
    label: e.name,
    world: e.world as [number, number, number],
    color: collapsed.has(e.name) ? WARN_COLOR : NET_COLOR,
  }));
  const compare = (inspection.compare?.electrodes ?? []).map((e, i) => ({
    id: `compare:${i}`,
    label: `${e.name} (${inspection.compare?.net})`,
    world: e.world as [number, number, number],
    color: COMPARE_COLOR,
  }));
  return [...net, ...compare];
}

export function mm(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(1);
}
