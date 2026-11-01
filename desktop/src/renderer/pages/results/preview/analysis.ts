/**
 * An analyzer run's `results.csv` → the Ex-search-shaped preview (header block, key numbers,
 * figures, files).
 *
 * Shape read from a real run: `derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/Analyses/Mesh/
 * cortical_2regions_DK40_71a9008a/results.csv` — two columns, `Metric,Value`, 22 rows, four of
 * them strings (`field_name`, `region_name`, `space`, `analysis_type`) and the rest float64 repr
 * served back as *strings* by `GET /api/catalog/analyses/{name}/summary`.
 *
 * The maintainer's note on the old pane: a 22-row METRIC/VALUE table is the file, not a reading of
 * it. The reader wants the ROI mean and max first, the percentiles and the focality extent second,
 * and never wants to count digits. So the four descriptive rows become the header block, the rest
 * become four small labelled grids in the order a result is read, and any metric a future analyzer
 * adds falls through to `extras` rather than being silently dropped.
 *
 * Units. Field values carry the unit `tit.constants.FIELD_REGISTRY` gives the analysed field
 * (`field_name`): V/m for the envelopes, `hf_peak` and `hf_rms`, W/m³ for
 * `hf_power_density`. `focality_*_area` is
 * cm² in **mesh** space and cm³ in **voxel** space — the field name says "area" for both, which is
 * the naming SCI-03 deliberately kept when it fixed the voxel divisor; the label here says which
 * one this run is, because that is the only place the reader can learn it.
 * `total_area_or_volume` is mm²/mm³ and was never rescaled (SCI-03 again).
 *
 * Whole-tissue numbers. `gm_*` and `percentile_*` describe the whole analysed tissue, not the ROI
 * (`tit/analyzer/analyzer.py` AnalysisResult): the grey-matter surface in mesh space, the selected
 * tissue (GM, WM or both — `results.csv` names it in its `tissue` row) in voxel space. They are one group
 * titled by that tissue, so a whole-tissue 99.9th percentile above the ROI maximum does not read as
 * an ROI percentile. `focality_X_area` is the extent at or above X % of that 99.9th percentile.
 *
 * Carrier metrics. An analysis of a modulation field also reports the stimulation (carrier)
 * intensity's focality over the same elements: `hf_peak_focality` (hf_peak), `hf_rms_focality` (hf_rms),
 * `ti_selectivity` = `roi_focality / hf_peak_focality` and the `hf_peak_focality_*_area` hot spot. When one
 * cannot be computed its rows are absent and `carrier_note` says why; the pane shows it as one
 * muted line (`carrierNote`).
 *
 * On demand. A field the simulation did not save (or the NIfTI a voxel analysis reads) is produced
 * by the analysis from the channel meshes and kept; `on_demand_note` says what was, in the words
 * the analysis logged, and the pane shows it as one muted line (`onDemandNote`).
 */
import { fieldLabel, fieldSpecForName } from "../../analyzer/fields";
import { formatCount, formatMetric, type KeyNumber } from "./metrics";
import type { SummaryRow } from "./simulation";

export interface TableLike {
  columns: string[];
  rows: (string | number | null)[][];
}

export interface MetricGroup {
  title: string;
  metrics: KeyNumber[];
}

export interface AnalysisView {
  /** The compact key/value block at the top — what this analysis *is*. */
  header: SummaryRow[];
  /** The labelled number grids, in reading order. Empty groups are dropped. */
  groups: MetricGroup[];
  /** Metrics this projection does not name, so a newer analyzer's rows are still shown. */
  extras: SummaryRow[];
  /** "mesh" | "voxel" | undefined — decides the focality unit. */
  space?: string;
  /** Why carrier metrics are missing (`carrier_note`), shown as one muted line; absent when none are. */
  carrierNote?: string;
  /** What the analysis produced because the simulation had not saved it (`on_demand_note`). */
  onDemandNote?: string;
}

/** `Metric,Value` rows → a lookup. A table with other columns yields an empty map. */
export function metricMap(table: TableLike | undefined): Map<string, string> {
  const out = new Map<string, string>();
  if (!table) return out;
  const key = table.columns.findIndex((c) => c.toLowerCase() === "metric");
  const val = table.columns.findIndex((c) => c.toLowerCase() === "value");
  if (key === -1 || val === -1) return out;
  for (const row of table.rows) {
    const name = row[key];
    if (typeof name !== "string" || name.trim() === "") continue;
    const raw = row[val];
    out.set(name.trim(), raw === null || raw === undefined ? "" : String(raw));
  }
  return out;
}

function numberOf(map: Map<string, string>, key: string): number | undefined {
  const raw = map.get(key);
  if (raw === undefined || raw.trim() === "") return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

/** Human wording for the analyzer's own vocabulary. Unknown values pass through verbatim. */
const SPACE_LABELS: Record<string, string> = { mesh: "Mesh (surface)", voxel: "Voxel (volume)" };
const TYPE_LABELS: Record<string, string> = {
  cortical: "Cortical region",
  spherical: "Spherical ROI",
  subcortical: "Subcortical region",
  whole_head: "Whole head",
};

/** The unit of `focality_*_area` for a given analysis space (SCI-03). */
export function focalityUnit(space: string | undefined): string {
  return space === "voxel" ? "cm³" : "cm²";
}

/** The unit of a field's values: `FIELD_REGISTRY`'s, V/m for a field it does not list. */
export function fieldUnit(field: string | undefined): string {
  return (field && fieldSpecForName(field)?.units) || "V/m";
}

/** What the whole-tissue numbers are taken over: the GM surface (mesh) or the analysed volume. */
export function wholeTissueTitle(space: string | undefined): string {
  return space === "voxel" ? "Whole analysed tissue" : "Whole grey matter";
}

/** The unit of `total_area_or_volume` for a given analysis space. */
export function extentUnit(space: string | undefined): string {
  return space === "voxel" ? "mm³" : "mm²";
}

/** Metrics the header block and the grids below consume; everything else falls to `extras`. */
const NAMED = new Set([
  "field_name",
  "region_name",
  "space",
  "analysis_type",
  "roi_mean",
  "roi_max",
  "roi_min",
  "roi_focality",
  "percentile_95",
  "percentile_99",
  "percentile_99_9",
  "gm_mean",
  "gm_max",
  "normal_mean",
  "normal_max",
  "normal_focality",
  "focality_50_area",
  "focality_75_area",
  "focality_90_area",
  "focality_95_area",
  "n_elements",
  "total_area_or_volume",
  "hf_peak_roi_mean",
  "hf_peak_gm_mean",
  "hf_peak_focality",
  "hf_rms_roi_mean",
  "hf_rms_gm_mean",
  "hf_rms_focality",
  "ti_selectivity",
  "hf_peak_focality_50_area",
  "hf_peak_focality_75_area",
  "hf_peak_focality_90_area",
  "hf_peak_focality_95_area",
  "carrier_note",
  "on_demand_note",
]);

function keep(metrics: (KeyNumber | undefined)[]): KeyNumber[] {
  return metrics.filter((m): m is KeyNumber => m !== undefined);
}

function metric(
  label: string,
  value: number | undefined,
  unit?: string,
  extra?: Partial<KeyNumber>,
): KeyNumber | undefined {
  const text = formatMetric(value, unit);
  return text === undefined ? undefined : { label, value: text, ...extra };
}

/**
 * The whole projection. `context` carries what the catalog knows and the CSV does not — which
 * subject and which simulation this analysis belongs to.
 */
export function analysisView(
  table: TableLike | undefined,
  context: { subject?: string; simulation?: string; roi?: string } = {},
): AnalysisView {
  const map = metricMap(table);
  const space = map.get("space")?.trim() || undefined;
  const unit = fieldUnit(map.get("field_name")?.trim());

  const header: SummaryRow[] = [];
  if (context.subject) header.push({ label: "Subject", value: context.subject });
  if (context.simulation) header.push({ label: "Simulation", value: context.simulation });
  const field = map.get("field_name");
  if (field) header.push({ label: "Field", value: fieldLabel(field.trim()) });
  if (space) header.push({ label: "Space", value: SPACE_LABELS[space] ?? space });
  const type = map.get("analysis_type");
  if (type) header.push({ label: "Analysis", value: TYPE_LABELS[type] ?? type });
  const region = map.get("region_name") || context.roi;
  if (region) header.push({ label: "Region", value: region.replace(/\+/g, " + ") });

  const fu = focalityUnit(space);
  const groups: MetricGroup[] = [
    {
      title: "ROI",
      metrics: keep([
        metric("Mean", numberOf(map, "roi_mean"), unit, { lead: true }),
        metric("Max", numberOf(map, "roi_max"), unit, { lead: true }),
        metric("Min", numberOf(map, "roi_min"), unit),
        metric("Focality ratio", numberOf(map, "roi_focality")),
      ]),
    },
    {
      title: wholeTissueTitle(space),
      metrics: keep([
        metric("Mean", numberOf(map, "gm_mean"), unit),
        metric("Max", numberOf(map, "gm_max"), unit),
        metric("95th percentile", numberOf(map, "percentile_95"), unit),
        metric("99th percentile", numberOf(map, "percentile_99"), unit),
        metric("99.9th percentile", numberOf(map, "percentile_99_9"), unit),
      ]),
    },
    {
      title: "Normal component",
      metrics: keep([
        metric("Mean", numberOf(map, "normal_mean"), unit),
        metric("Max", numberOf(map, "normal_max"), unit),
        metric("Focality ratio", numberOf(map, "normal_focality")),
      ]),
    },
    {
      title: `Focality extent · ${fu}`,
      metrics: keep([
        metric(`≥ 50 % of ${space === "voxel" ? "tissue" : "GM"} 99.9th percentile`, numberOf(map, "focality_50_area"), fu),
        metric("≥ 75 %", numberOf(map, "focality_75_area"), fu),
        metric("≥ 90 %", numberOf(map, "focality_90_area"), fu),
        metric("≥ 95 %", numberOf(map, "focality_95_area"), fu),
      ]),
    },
    {
      // hf_peak and hf_rms are V/m whatever field was analysed (tit/analyzer AnalysisResult).
      title: "Stimulation (carrier) focality",
      metrics: keep([
        metric("TI selectivity", numberOf(map, "ti_selectivity"), undefined, { lead: true }),
        metric("HF_{peak} focality ratio", numberOf(map, "hf_peak_focality")),
        metric("HF_{rms} focality ratio", numberOf(map, "hf_rms_focality")),
        metric("HF_{peak} ROI mean", numberOf(map, "hf_peak_roi_mean"), "V/m"),
        metric("HF_{peak} GM mean", numberOf(map, "hf_peak_gm_mean"), "V/m"),
        metric("HF_{rms} ROI mean", numberOf(map, "hf_rms_roi_mean"), "V/m"),
        metric("HF_{rms} GM mean", numberOf(map, "hf_rms_gm_mean"), "V/m"),
      ]),
    },
    {
      title: `Carrier hot spot · ${fu}`,
      metrics: keep([
        metric(`HF_{peak} ≥ 50 % of its 99.9th percentile`, numberOf(map, "hf_peak_focality_50_area"), fu),
        metric("≥ 75 %", numberOf(map, "hf_peak_focality_75_area"), fu),
        metric("≥ 90 %", numberOf(map, "hf_peak_focality_90_area"), fu),
        metric("≥ 95 %", numberOf(map, "hf_peak_focality_95_area"), fu),
      ]),
    },
    {
      title: "ROI extent",
      metrics: keep([
        map.has("n_elements")
          ? { label: space === "voxel" ? "Voxels" : "Elements", value: formatCount(numberOf(map, "n_elements")) ?? "—" }
          : undefined,
        metric(space === "voxel" ? "Volume" : "Area", numberOf(map, "total_area_or_volume"), extentUnit(space)),
      ]),
    },
  ].filter((g) => g.metrics.length > 0);

  const extras: SummaryRow[] = [];
  for (const [name, value] of map) {
    if (NAMED.has(name)) continue;
    const asNumber = Number(value);
    extras.push({
      label: name.replace(/_/g, " "),
      value: value !== "" && Number.isFinite(asNumber) ? (formatMetric(asNumber) ?? value) : value,
    });
  }

  const carrierNote = map.get("carrier_note")?.trim() || undefined;
  const onDemandNote = map.get("on_demand_note")?.trim() || undefined;
  return { header, groups, extras, space, carrierNote, onDemandNote };
}
