/**
 * The EEG-net join for the Ex/mEx family: one net identity, derived from two catalog endpoints
 * that spell the same net two different ways.
 *
 * `GET /api/catalog/leadfields` reports `net` as the **bare** name parsed out of the HDF5
 * filename (`tit/opt/leadfield.py::list_leadfields` splits `ernie_leadfield_<net>.hdf5`), while
 * `GET /api/catalog/eeg-nets` reports `name` as the **real cap filename**
 * (`tit/catalog.py::eeg_nets` returns `pm.list_eeg_caps()` entries, i.e. `<net>.csv`). On the real
 * project that is `"EEG10-10_UI_Jurak_2007"` against `"EEG10-10_UI_Jurak_2007.csv"`, so an
 * equality join between them never matches: the page derived its electrode list from the net the
 * leadfield strip had selected, found nothing, and every electrode bucket offered zero options —
 * Ex/mEx could not be run from the UI at all against a real leadfield (lane S2's `real/ex.spec.ts`
 * / `real/mex.spec.ts` both timed out waiting for the option "Fp1"). The mock server hides this:
 * its fixtures spell both sides bare.
 *
 * The rule this module enforces: **a net is identified by its bare name everywhere in this page**
 * — the value the strip selects, the key the electrode lookup uses, and the `eeg_net` a leadfield
 * job is submitted with (`LeadfieldGenerator` appends `.csv` itself, so a `.csv`-suffixed value
 * there would ask for `<net>.csv.csv`, the same double-suffix bug S2 fixed in the source panel).
 */
import type { EegNet, Leadfield } from "./api";
import type { OptimizerRow } from "./rows";

/** The bare net name: `"EEG10-10_UI_Jurak_2007.csv"` and `"EEG10-10_UI_Jurak_2007"` are one net. */
export function netKey(name: string): string {
  return name.replace(/\.csv$/i, "");
}

/** The leadfield entry for `net`, whichever way either side spells it. */
export function leadfieldFor(leadfields: Leadfield[] | undefined, net: string | null): Leadfield | undefined {
  if (!net) return undefined;
  const key = netKey(net);
  return (leadfields ?? []).find((lf) => netKey(lf.net) === key);
}

/** The HDF5 path for `net`, or `null` when this subject has no computed leadfield for it. */
export function leadfieldPathFor(leadfields: Leadfield[] | undefined, net: string | null): string | null {
  const lf = leadfieldFor(leadfields, net);
  return lf?.exists ? lf.path : null;
}

/**
 * The electrode a leadfield was computed with, in a few words: "ellipse 8×8 mm, gel 1 mm". A
 * leadfield with no sidecar (`electrode: null`) says so rather than borrowing today's defaults — it
 * may have been computed with any electrode.
 */
export function leadfieldElectrodeLabel(lf: Pick<Leadfield, "electrode"> | undefined): string {
  const e = lf?.electrode;
  if (!e) return "electrode not recorded";
  const [w, h] = e.electrode_dimensions;
  return `${e.electrode_shape} ${w}×${h} mm, gel ${e.gel_thickness} mm`;
}

/** The net's electrode labels — the options every Ex/mEx bucket and the Ex pool are filled from. */
export function electrodesForNet(nets: EegNet[] | undefined, net: string | null): string[] {
  if (!net) return [];
  const key = netKey(net);
  return (nets ?? []).find((n) => netKey(n.name) === key)?.electrodes ?? [];
}

/**
 * The strip's options: every net this subject has, bare, with the ones that already have a
 * leadfield first. Both sources are unioned (de-duplicated by `netKey`) so a net with a leadfield
 * is offered even when the cap CSV is gone, and a net without one is still selectable — that is
 * how the strip's "Generate" button is reachable at all.
 */
export function netOptions(leadfields: Leadfield[] | undefined, nets: EegNet[] | undefined): { value: string; label: string }[] {
  const seen = new Set<string>();
  const out: { value: string; label: string }[] = [];
  for (const name of [...(leadfields ?? []).filter((lf) => lf.exists).map((lf) => lf.net), ...(nets ?? []).map((n) => n.name), ...(leadfields ?? []).map((lf) => lf.net)]) {
    const key = netKey(name);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ value: key, label: key });
  }
  return out;
}

/** The net a freshly opened page starts on: the first one that already has a leadfield. */
export function defaultNet(leadfields: Leadfield[] | undefined, nets: EegNet[] | undefined): string | null {
  const ready = (leadfields ?? []).find((lf) => lf.exists);
  if (ready) return netKey(ready.net);
  const first = (leadfields ?? [])[0]?.net ?? (nets ?? [])[0]?.name;
  return first ? netKey(first) : null;
}

/**
 * An Ex/mEx row with every electrode its net does not have taken out, and the labels taken out
 * (first-seen order, once each).
 *
 * The rule a net switch follows: a label is kept when the net's electrode list (`electrodesForNet`,
 * the list every bucket is filled from) has it, and dropped otherwise -- the new net's leadfield
 * has no field for it, so the job could only fail on the server. A bucket left empty, or a pool
 * left under four, is then refused by the row gate's own sentence (`rowFormReason`). Both the Ex
 * buckets and pool and the mEx buckets are reconciled, since a row carries both forms.
 *
 * An empty `electrodes` means the net's list is unknown here (the nets listing has not arrived, or
 * a leadfield's cap CSV is gone): nothing is dropped, and the server's preflight and the runner
 * judge the labels against the leadfield instead. A Flex row's net is a mapping net, not a
 * leadfield, so a Flex row is returned as is. The same row object comes back when nothing is
 * dropped.
 */
export function keepElectrodesOnNet(row: OptimizerRow, electrodes: readonly string[]): { row: OptimizerRow; dropped: string[] } {
  if (row.method !== "ex" || electrodes.length === 0) return { row, dropped: [] };
  const onNet = new Set(electrodes);
  const dropped: string[] = [];
  const keep = (labels: string[] | undefined): string[] =>
    (labels ?? []).filter((label) => {
      if (onNet.has(label)) return true;
      if (!dropped.includes(label)) dropped.push(label);
      return false;
    });
  const buckets = (b: Record<string, string[]>) => Object.fromEntries(Object.entries(b).map(([key, labels]) => [key, keep(labels)]));
  const ex = { ...row.ex, buckets: buckets(row.ex.buckets), pool: keep(row.ex.pool) };
  const mex = { ...row.mex, buckets: buckets(row.mex.buckets) };
  return dropped.length === 0 ? { row, dropped } : { row: { ...row, ex, mex }, dropped };
}
