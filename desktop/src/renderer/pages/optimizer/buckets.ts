/**
 * The Ex/mEx **bucket ↔ electrode** model: which hue a bucket is drawn in, which hue each
 * electrode of the net therefore gets, and what clicking an electrode in the scene pane means.
 *
 * Pure, renderer-free and DOM-free for the same reason `_shared/scene/model.ts` is: the pane and
 * the row editor are two views of ONE selection (the row's `ExFormState` / `MExFormState`), and
 * the thing that can silently disagree is the mapping between them. A function from a bucket key
 * to a channel index can be checked against arithmetic; a dot on a scalp cannot.
 *
 * Three rules, each with the failure it prevents:
 *
 *  - **A bucket's hue is its channel, not its pole.** `e1_plus` and `e1_minus` are both channel 1
 *    and both draw in the channel-1 Okabe-Ito blue, exactly as the Simulator's montage pane paints
 *    both electrodes of pair 1 the same. The pane's own contract is "an electrode's colour is its
 *    whole state — no ring, no outline, no second glyph" (`ScenePane.tsx` header), so inventing a
 *    filled/hollow variant for the pole would be a second glyph the montage pane does not have and
 *    the shader does not draw.
 *  - **The pool is one hue.** Ex's "All combinations" mode has no buckets: every electrode in the
 *    pool can land in any position, so channel 1 is the honest colour for all of them.
 *  - **A click toggles within the active bucket only.** It never moves an electrode out of another
 *    bucket: `e1_plus` and `e2_plus` may legitimately share an electrode, and a click that quietly
 *    emptied another bucket would delete a search space the user typed.
 */
import { BUCKET_LABELS, EX_BUCKET_KEYS, MEX_BUCKET_KEYS } from "./exConfig";

/** The key the pool is addressed by, so one `activeBucket` string covers both Ex modes. */
export const POOL_KEY = "pool";

/** What the pane is currently colouring: an ordered bucket list, or Ex's single pool. */
export interface BucketView {
  /** The bucket keys in form order, or `[POOL_KEY]`. */
  keys: readonly string[];
  /** Bucket key → the electrodes in it. */
  values: Record<string, string[]>;
}

/**
 * The channel (pair) index a bucket is drawn in: `e<N>_plus` and `e<N>_minus` are both channel
 * `N - 1`. Anything unrecognised — the pool included — is channel 0.
 */
export function bucketChannel(key: string): number {
  const match = /^e(\d+)_(plus|minus)$/.exec(key);
  return match ? Math.max(0, Number(match[1]) - 1) : 0;
}

/** `"E1+"`, or `"Pool"` for the pool — the name the legend chip carries. */
export function bucketLabel(key: string): string {
  return key === POOL_KEY ? "Pool" : (BUCKET_LABELS[key] ?? key);
}

/** The view for a row: Ex's four buckets or its pool, or mEx's eight. */
export function exBucketView(form: { electrodeMode: "bucketed" | "all"; buckets: Record<string, string[]>; pool: string[] }): BucketView {
  return form.electrodeMode === "bucketed"
    ? { keys: EX_BUCKET_KEYS, values: form.buckets }
    : { keys: [POOL_KEY], values: { [POOL_KEY]: form.pool } };
}

export function mexBucketView(form: { buckets: Record<string, string[]> }): BucketView {
  return { keys: MEX_BUCKET_KEYS, values: form.buckets };
}

/**
 * Electrode name → the channel its marker is painted in.
 *
 * An electrode in two buckets takes the FIRST bucket's channel, in form order, because a marker
 * has one colour and the first bucket is the one the user filled first. Electrodes in no bucket
 * are absent from the map and draw neutral grey, which is what "unassigned" looks like everywhere
 * else in the app.
 */
export function bucketChannels(view: BucketView): Record<string, number> {
  const out: Record<string, number> = {};
  for (const key of view.keys) {
    const channel = bucketChannel(key);
    for (const name of view.values[key] ?? []) if (!(name in out)) out[name] = channel;
  }
  return out;
}

/** One legend chip per bucket: its key, its name, its channel hue and how full it is. */
export interface BucketLegendRow {
  key: string;
  label: string;
  channel: number;
  count: number;
}

export function bucketLegendRows(view: BucketView): BucketLegendRow[] {
  return view.keys.map((key) => ({
    key,
    label: bucketLabel(key),
    channel: bucketChannel(key),
    count: (view.values[key] ?? []).length,
  }));
}

/**
 * Clicking electrode `name` while bucket `key` is active: **toggle it into that bucket**, the same
 * edit the row editor's own selection list makes, so the pane and the form run one operation and
 * cannot disagree about what "toggle" means (the pane never holds the selection).
 *
 * Returns the SAME object when the view has no such bucket, so a caller's identity check is a
 * correct "did anything change?" test.
 */
export function toggleBucketElectrode(view: BucketView, key: string, name: string): Record<string, string[]> {
  if (!view.keys.includes(key)) return view.values;
  const current = view.values[key] ?? [];
  const next = current.includes(name) ? current.filter((e) => e !== name) : [...current, name];
  return { ...view.values, [key]: next };
}

/** The bucket a fresh row starts on: E1+, or the pool when that is all there is. */
export function defaultBucketKey(view: BucketView): string {
  return view.keys[0] ?? POOL_KEY;
}

/** The active bucket, falling back to the default when the stored one is not in this view (the
 *  user switched the row from bucketed to pooled, or from Ex to mEx). */
export function resolveActiveBucket(view: BucketView, stored: string | null): string {
  return stored && view.keys.includes(stored) ? stored : defaultBucketKey(view);
}
