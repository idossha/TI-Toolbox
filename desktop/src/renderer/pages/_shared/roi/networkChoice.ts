/**
 * The four ways of choosing a network, as pure functions over region-name pairs: each ends in the
 * one definition every page shares, `tit.tract`'s `Selection(kind="edges")`. No metric is ranked
 * here beyond the one the user names, and none is suggested.
 */
import type { components } from "../../../api/schema";
import { NETWORK_NAME_RE, type NetworkHow, type NetworkRoiValue } from "./types";

export type TractPreset = components["schemas"]["TractPreset"];
export type TractConnection = components["schemas"]["TractConnection"];
type Pair = [string, string];
interface EdgeLike {
  region_a: string;
  region_b: string;
  n: number;
}

/** `tit.blender.network_setup.WITH_OPPOSITE_SUFFIX`. */
const WITH_OPPOSITE_SUFFIX = "_with_opposite";

/** What a top-N list may be ordered by, named as the caption and tables name them. */
export const CONNECTION_METRICS: { value: keyof TractConnection; label: string }[] = [
  { value: "align_index", label: "Median align_index" },
  { value: "ti_along_mean", label: "Median ti_along (V/m)" },
  { value: "ti_avg_mean", label: "Median ti_avg (V/m)" },
  { value: "ti_max_mean", label: "Median TI_max (V/m)" },
  { value: "n", label: "Streamline count" },
];

const pair = (edge: EdgeLike): Pair => [edge.region_a, edge.region_b];

/** Every edge joining a `from` region to a `to` region; with no `to`, every edge of a `from` region. */
export function pairsFromTo(edges: readonly EdgeLike[], from: readonly string[], to: readonly string[], minN: number): Pair[] {
  const a = new Set(from);
  const b = new Set(to);
  const joins = (x: string, y: string) => a.has(x) && (b.size === 0 || b.has(y));
  return edges.filter((e) => e.n >= minN && (joins(e.region_a, e.region_b) || joins(e.region_b, e.region_a))).map(pair);
}

/** The `topN` edges highest in `metric`, of at least `minN` streamlines; ties in a stable order. */
export function strongestPairs(rows: readonly TractConnection[], metric: keyof TractConnection, topN: number, minN: number): Pair[] {
  const score = (row: TractConnection) => Number(row[metric]);
  const name = (row: TractConnection) => `${row.region_a}|${row.region_b}`;
  return rows
    .filter((row) => row.n >= minN && Number.isFinite(score(row)))
    .sort((x, y) => score(y) - score(x) || name(x).localeCompare(name(y)))
    .slice(0, topN)
    .map(pair);
}

const samePair = (a: readonly string[], b: readonly string[]): boolean => (a[0] === b[0] && a[1] === b[1]) || (a[0] === b[1] && a[1] === b[0]);

/** Streamlines and edges among `pairs`, from whichever rows list them. */
export function pairTotals(rows: readonly EdgeLike[], pairs: readonly (readonly string[])[]): { streamlines: number; edges: number } {
  const found = rows.filter((row) => pairs.some((p) => samePair(p, [row.region_a, row.region_b])));
  return { streamlines: found.reduce((sum, row) => sum + row.n, 0), edges: found.length };
}

/** The same two lists of region pairs, whichever way round and in whatever order. */
export function samePairSet(a: readonly (readonly string[])[], b: readonly (readonly string[])[]): boolean {
  const key = (p: readonly string[]) => [...p].sort().join("|");
  const left = new Set(a.map(key));
  return left.size === new Set(b.map(key)).size && b.every((p) => left.has(key(p)));
}

/** `lh.insula` -> `lh_insula`: what a Selection's name allows. */
function slug(region: string): string {
  return region.replace(/[^A-Za-z0-9_-]+/g, "_");
}

function listSlug(regions: readonly string[]): string {
  return regions.length === 1 ? slug(regions[0]!) : `${regions.length}_regions`;
}

/** A name from the choice, with no more in it than the choice said. Always a valid Selection name. */
export function autoNetworkName(value: Pick<NetworkRoiValue, "how" | "preset" | "presetSameSide" | "includeOpposite" | "seeds" | "to" | "pairs" | "metric" | "topN">): string {
  const seeds = value.seeds;
  let name = "";
  switch (value.how) {
    case "preset":
      name = (value.preset ?? "") + (value.preset && value.presetSameSide && value.includeOpposite ? WITH_OPPOSITE_SUFFIX : "");
      break;
    case "region":
      if (seeds.length) name = (value.to ?? []).length ? `${listSlug(seeds)}_to_${listSlug(value.to!)}` : listSlug(seeds);
      break;
    case "strongest":
      if (value.metric) name = `top_${value.topN ?? 10}_by_${value.metric}`;
      break;
    default:
      if (value.pairs.length === 1) name = `${slug(value.pairs[0]![0])}_${slug(value.pairs[0]![1])}`;
      else if (value.pairs.length > 1) name = `${listSlug(seeds)}_${value.pairs.length}_edges`;
  }
  name = slug(name).slice(0, 96);
  return NETWORK_NAME_RE.test(name) ? name : "";
}

/** The value with its choice applied, its name following until the user types one. */
export function withChoice(value: NetworkRoiValue, patch: Partial<NetworkRoiValue>, edit: (value: NetworkRoiValue, patch: Partial<NetworkRoiValue>) => NetworkRoiValue): NetworkRoiValue {
  const next = { ...value, ...patch };
  return edit(value, value.nameEdited ? patch : { ...patch, name: autoNetworkName(next) });
}

/** A preset's edges: same-hemisphere ones alone, unless the opposite ones were asked for. */
export function presetPairs(preset: TractPreset, includeOpposite: boolean): Pair[] {
  return [...preset.pairs, ...(includeOpposite ? preset.opposite_pairs : [])] as Pair[];
}

/** Streamlines and edges the preset gives in this state. */
export function presetTotals(preset: TractPreset, includeOpposite: boolean): { streamlines: number; edges: number } {
  return includeOpposite
    ? { streamlines: preset.n_streamlines + preset.n_opposite, edges: preset.n_edges + preset.opposite_pairs.length }
    : { streamlines: preset.n_streamlines, edges: preset.n_edges };
}

/** `tit.tract.presets.removed_sentence`, for the picker's count line: what same-side left out. */
export function removedSentence(preset: TractPreset): string {
  const count = (n: number) => n.toLocaleString("en-US");
  return (
    `${count(preset.n_streamlines)} of ${count(preset.n_streamlines + preset.n_opposite)}; ` +
    `${count(preset.n_opposite)} opposite-hemisphere removed ` +
    `(right thalamus to left cortex ${count(preset.right_thalamus_to_left_cortex)}, ` +
    `left thalamus to right cortex ${count(preset.left_thalamus_to_right_cortex)})`
  );
}

export const HOW_LABELS: Record<NetworkHow, string> = {
  preset: "Preset",
  region: "By region",
  connection: "By connection",
  strongest: "Strongest here",
};

/** A `Selection` of kind `edges`, the shape the render, the assess stage and the mask all read. */
export function networkSelection(value: NetworkRoiValue): { name: string; kind: "edges"; regions: string[]; pairs: Pair[] } {
  // A top-N list was chosen by no region; the render picks what to light from its busiest ends.
  return { name: value.name, kind: "edges", regions: value.how === "strongest" ? [] : value.seeds, pairs: value.pairs };
}
