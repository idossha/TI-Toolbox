/**
 * "Flex result" as a job **source** — the placements a completed flex-search can be simulated in.
 *
 * The tab this file used to be is gone (2026-09-06 jobs rework): a job row picks its source in its
 * own Source cell, so what is left here is the pure model the row's EEG-net and Montage cells read
 * (`JobsTable`'s `renderNetCell` / `setRowFlexRun`).
 *
 * Where the electrodes come from: **not** `flex_meta.json`. A flex run's manifest records the
 * goal, the ROI and the optimiser's score, and nothing at all about the electrodes it found — so
 * the earlier `manifest.electrodes` read here was always `undefined`, which disabled every row's
 * checkbox and made the whole tab unclickable (simulator PARITY.md #4, closed by this file).
 *
 * The electrodes live beside the manifest in the run directory, and `tit/catalog.py::flex_runs`
 * now surfaces both forms the toolbox can simulate:
 *
 *   - `run.mappings` — one entry per `electrode_mapping_<net>.json` the run has, i.e. the result
 *     already snapped onto that EEG cap's labels (`Montage.Mode.FLEX_MAPPED`);
 *   - `run.optimized` — the free XYZ pairs from `electrode_positions.json`, which every flex run
 *     writes (`Montage.Mode.FLEX_FREE`).
 *
 * A run therefore offers at least the free placement, and the per-row select is the choice between
 * them. Both are resolved here rather than at submit time because `POST /api/jobs`' `JobSpec` has
 * no `montage_sources` field: a submitted job carries a fully-resolved `Montage`.
 */
import type { FlexMapping, FlexRun } from "./api";
import { defaultCurrents } from "./types";

/** The free-XYZ placement's option value; anything else is an EEG-net filename. */
export const OPTIMIZED = "__optimized__";

/**
 * A mapped electrode further than this from where the optimiser put it is flagged (mm).
 *
 * Mapping snaps each optimised electrode to a net site (Hungarian assignment, Euclidean mm).
 * 20 mm is about one inter-electrode spacing of a dense net (HydroCel, BioSemi-128) and over
 * twice the default flex electrode's 8 mm diameter: past it the mapped electrode no longer
 * covers the scalp the optimiser chose, so the mapped montage is a different montage. On
 * Dataset 000 sparse or mis-registered nets snap 44-77 mm (`tit.catalog.read_flex_mapping`'s
 * `max_snap_mm`; tests/numerical/test_flex_mapping_snap_realdata.py prints them).
 */
export const SNAP_WARN_MM = 20;

/** `tit.catalog.read_flex_mapping` adds `max_snap_mm` (left out when unknown); the contract's
 *  `FlexMapping` does not list it yet. */
type MappingWithSnap = FlexMapping & { max_snap_mm?: number | null };

export interface FlexPlacement {
  /** `OPTIMIZED`, or the EEG net whose mapping this is. */
  value: string;
  label: string;
  pairs?: [string, string][];
  xyzPairs?: [[number, number, number], [number, number, number]][];
  /** The largest distance (mm) a mapped electrode moved from its optimised position, if known. */
  maxSnapMm?: number;
}

/** Every placement a run can be simulated in: one per mapped net, then the free XYZ one. */
export function placementsFor(run: FlexRun): FlexPlacement[] {
  const out: FlexPlacement[] = [];
  for (const mapping of (run.mappings ?? []) as MappingWithSnap[]) {
    const pairs = (mapping.pairs ?? [])
      .filter((p) => p.length === 2)
      .map((p) => [p[0], p[1]] as [string, string]);
    if (pairs.length === 0) continue;
    const snap = mapping.max_snap_mm;
    out.push({
      value: mapping.eeg_net,
      label: mapping.eeg_net.replace(/\.csv$/, ""),
      pairs,
      ...(typeof snap === "number" && Number.isFinite(snap) ? { maxSnapMm: snap } : {}),
    });
  }
  const optimized = (run.optimized ?? [])
    .filter((p) => p.length === 2 && p[0]?.length === 3 && p[1]?.length === 3)
    .map((p) => [p[0], p[1]] as [[number, number, number], [number, number, number]]);
  if (optimized.length > 0) out.push({ value: OPTIMIZED, label: "Optimised positions (XYZ)", xyzPairs: optimized });
  return out;
}

/**
 * The run's own currents as a row's wire string: its optimised `current_split`, else its
 * `current_mA` per channel, else 1 mA per channel. Same order as the server's
 * `tit.sim.montage_sources.flex_currents` (`resolve_flex_simulation`); both are pinned by
 * `tests/fixtures/flex_currents.json`.
 */
export function flexCurrents(run: FlexRun | undefined, numPairs: number): string {
  const manifest = (run?.manifest ?? {}) as { current_split?: number[] | null; current_mA?: number | null };
  if (manifest.current_split?.length) return manifest.current_split.join(",");
  const mA = Number(manifest.current_mA);
  return mA > 0 ? Array(Math.max(2, numPairs)).fill(String(mA)).join(",") : defaultCurrents(numPairs);
}

/**
 * The sentence a mapped placement shows when it moved an electrode more than `SNAP_WARN_MM`.
 * The distance is judged at the 0.1 mm the sentence prints, so it never reads "20.0 mm (more
 * than 20 mm)".
 */
export function snapWarning(placement: FlexPlacement | undefined): string | null {
  const snap = placement?.maxSnapMm;
  if (!placement || placement.value === OPTIMIZED || snap === undefined) return null;
  const shown = Math.round(snap * 10) / 10;
  if (!(shown > SNAP_WARN_MM)) return null;
  return (
    `Mapping onto ${placement.label} moves an electrode ${shown.toFixed(1)} mm from where the optimiser ` +
    `put it (more than ${SNAP_WARN_MM} mm), so this is not the optimised montage. ` +
    "Simulate the optimised positions, or map onto a denser net."
  );
}

/**
 * The snap warning for a flex job mapped onto `net`, under the job's pairs. Reads the run's own
 * `mappings` (a net mapped on demand appears there once the flex-runs list refetches).
 */
export function FlexSnapWarning({ run, net }: { run: FlexRun | undefined; net: string | undefined }) {
  const stem = (name: string) => name.replace(/\.csv$/, "");
  const placement = run && net ? placementsFor(run).find((p) => p.value !== OPTIMIZED && stem(p.value) === stem(net)) : undefined;
  const text = snapWarning(placement);
  if (!text) return null;
  return (
    <span className="field-note" role="status" data-testid="flex-snap-warning" style={{ color: "var(--warning)" }}>
      {text}
    </span>
  );
}

