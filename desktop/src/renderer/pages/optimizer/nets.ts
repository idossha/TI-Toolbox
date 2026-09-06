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
 * how "Generate (≈40 min)" is reachable at all.
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

