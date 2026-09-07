/**
 * Number formatting for the Results preview's "Key numbers" grids.
 *
 * The analyzer writes its `results.csv` with full float64 repr — `0.07018370126141073` — and the
 * pane used to render all 22 of those verbatim in a METRIC/VALUE table. Sixteen significant digits
 * of a FEM field value are not a measurement; a TI field is quoted to three or four digits in every
 * paper the toolbox cites, and the extra thirteen only cost the column width the unit needs. So:
 * four significant digits, trailing zeros trimmed, and an exponent only where a fixed rendering
 * would be a run of zeros.
 */

/** A single labelled quantity in a "Key numbers" grid. */
export interface KeyNumber {
  label: string;
  /** Already formatted, unit included — see {@link formatMetric}. */
  value: string;
  /** True for the two or three numbers the reader came for; rendered larger. */
  lead?: boolean;
  /** Long-form note under the label (the focality unit caveat, for instance). */
  hint?: string;
}

/**
 * `0.07018370126141073` → `"0.07018"`, `1383362` → `"1.383e6"`, `0` → `"0"`.
 *
 * `significant` is the digit budget (4 by default). Values at or above 1e5, and non-zero values
 * below 1e-3, go to exponential — below that floor a fixed rendering is `0.0000…` and above that
 * ceiling it is a digit run no one reads.
 */
export function formatNumber(value: number, significant = 4): string {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude >= 1e5 || magnitude < 1e-3) {
    // `1.383e+6` → `1.383e6`; the `+` and the zero-padded exponent are noise in a table cell.
    return Number(value)
      .toExponential(significant - 1)
      .replace(/\.?0+e/, "e")
      .replace(/e\+?(-?)0*(\d)/, "e$1$2");
  }
  const fixed = Number(value.toPrecision(significant));
  return String(fixed);
}

/** {@link formatNumber} with a unit appended, separated by a normal space. */
export function formatMetric(
  value: number | undefined,
  unit?: string,
  significant = 4,
): string | undefined {
  if (value === undefined || !Number.isFinite(value)) return undefined;
  const text = formatNumber(value, significant);
  return unit ? `${text} ${unit}` : text;
}

/** An integer count — `4957`, never `4957.0` and never `4.957e3`. */
export function formatCount(value: number | undefined): string | undefined {
  if (value === undefined || !Number.isFinite(value)) return undefined;
  return Math.round(value).toLocaleString();
}
