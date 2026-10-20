/** The EEG caps panel's pure core: status wording, warnings and scene markers. Unit-tested in
 *  `tests/unit/caps-panel.test.ts`. */
import type { SemanticKind } from "../../../ui/Status";
import { SCENE_CATEGORICAL } from "../../../scene/palette";
import type { SceneMarker } from "../../_shared/scene/model";
import type { DataTableColumn } from "../../../ui/DataTable";
import type { CapElectrode, CapInspection, CapStatus } from "./api";

export function capStatus(cap: CapStatus): { label: string; kind: SemanticKind; title?: string } {
  if (!cap.on_subject) return { label: "not on subject", kind: "neutral" };
  if (cap.source === null) return { label: "on subject", kind: "success", title: "No MNI source: it cannot be re-applied here." };
  return { label: "on subject", kind: "success" };
}

const SOURCE_LABELS: Record<string, string> = { "ti-toolbox": "TI-Toolbox", simnibs: "SimNIBS", project: "uploaded" };

/** Who supplies the MNI cap; "subject only" for a net with no MNI file to re-apply from. */
export function sourceLabel(cap: CapStatus): string {
  return cap.source === null ? "subject only" : (SOURCE_LABELS[cap.source] ?? cap.source);
}

/** What the panel says when no subject in the project has a head model to put a cap on. */
export const NO_HEAD_MODEL = "No subject has a head model yet — run Pre-processing (charm) first.";

/**
 * The subject the panel opens on: the app's current subject when it has a head model (as the
 * Simulator seeds its first row), else the first subject that has one; null when none does.
 */
export function defaultCapsSubject(subjects: { id: string; has_m2m: boolean }[], current: string | null): string | null {
  const modelled = subjects.filter((s) => s.has_m2m).map((s) => s.id);
  return current && modelled.includes(current) ? current : (modelled[0] ?? null);
}

/** A cap as the rest of the app names a net: its file name without `.csv`. */
export function capLabel(name: string): string {
  return name.replace(/\.csv$/i, "");
}

/** When the subject's copy was written, as a local date; "—" when it is not on the subject. */
export function appliedDate(cap: CapStatus): string {
  return cap.subject_mtime == null ? "—" : new Date(cap.subject_mtime * 1000).toLocaleDateString();
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
    label: `${e.name} (${capLabel(inspection.compare?.net ?? "")})`,
    world: e.world as [number, number, number],
    color: COMPARE_COLOR,
  }));
  return [...net, ...compare];
}

export function mm(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(1);
}

export type ElectrodeRow = CapElectrode & { index: number };

/** Label, then the neighbour, then the two distances — headers in plain words with their units. */
export function electrodeColumns(compareNet: string | null): DataTableColumn<ElectrodeRow>[] {
  const dist = (key: keyof CapElectrode, header: string): DataTableColumn<ElectrodeRow> => ({
    accessorKey: key,
    header,
    numeric: true,
    cell: ({ getValue }) => mm(getValue() as number | null),
  });
  return [
    { accessorKey: "name", header: "Label" },
    { accessorKey: "nn_name", header: "Nearest electrode" },
    dist("nn_mm", "Spacing to nearest (mm)"),
    dist("scalp_mm", "Distance to scalp (mm)"),
    ...(compareNet
      ? [{ accessorKey: "compare_name", header: `Nearest in ${capLabel(compareNet)}` } as DataTableColumn<ElectrodeRow>, dist("compare_mm", "Distance to it (mm)")]
      : []),
  ];
}

/** The (i) on the Caps card — mirrors `docs/wiki/eeg-caps.md` "Apply a cap". */
export const CAPS_HELP = `**Apply** warps the MNI cap onto this head exactly as charm does at the end of a head-model build, and writes it to \`m2m_<subject>/eeg_positions/\`. Charm does not rerun; it takes seconds.

- **Source**: **TI-Toolbox** caps ship with TI-Toolbox (GSN-HydroCel, BioSemi), **SimNIBS** caps with SimNIBS, **uploaded** ones were added to this project, and **subject only** nets have no MNI file to re-apply.
- **on subject** / **not on subject**: whether the subject has this cap. **Applied** is the date it was written.
- **Re-apply all** refreshes every cap already on the subject, e.g. after an update fixes a cap.
- **Add MNI cap…** takes a CSV in MNI mm, one row per electrode: \`Electrode,x,y,z,name\` (SimNIBS's \`ElectrodeCaps_MNI\` format). It is kept with this project.`;

/** The (i) on the Inspect card — mirrors `docs/wiki/eeg-caps.md` "Inspect a net". */
export const INSPECT_HELP = `Checks how a net sits on this subject's scalp.

- **electrodes**: how many the net has.
- **spacing**: median and smallest distance from each electrode to its nearest neighbour.
- **scalp ≤**: the largest distance from an electrode to the scalp; near 0 means every electrode sits on the skin.
- **warning**: two electrodes closer than 2 mm (they collapsed onto one point, usually a cap in the wrong coordinate space) or a label used twice. Collapsed electrodes are red in the 3-D view; re-apply or fix the cap before using it.
- **Electrodes table**: each electrode's nearest neighbour and the distances. Click a column to sort, a row to ring that electrode in the 3-D view.
- **Compare with** draws a second net in orange and adds, per electrode, the nearest electrode of that net and the distance to it.`;
