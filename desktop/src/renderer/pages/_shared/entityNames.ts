/**
 * The server's two name rules, so a form refuses a name before Save or Run instead of after a 422
 * (or, for a flex run folder, after the run has been written under a name that breaks the listing
 * of every flex run of that subject).
 *
 *  - `isValidEntityName` is `tit.paths.is_valid_name` (`NAME_RE`): any user-supplied name that
 *    becomes one path component — simulation, run, montage, ROI, net, scene names.
 *  - `isSafeName` is `tit.catalog.is_safe_name`: the stricter rule every catalog WRITE holds a new
 *    name to — a saved montage, a free-hand placement, an ROI.
 *
 * Both are pinned to one table, `tests/fixtures/entity_names.json`, read by
 * `tests/test_entity_names.py` (against the Python functions) and
 * `desktop/tests/unit/entity-names.test.ts` (against these).
 */

/** `tit.paths.NAME_RE`. JavaScript's `$` (no `m` flag) matches only at the end of the input, as
 *  the server's `fullmatch` does: no trailing newline slips through. */
const NAME_RE = /^[A-Za-z0-9_-][A-Za-z0-9._ -]{0,127}$/;

/** `tit.catalog._SAFE_NAME_RE`. */
const SAFE_NAME_RE = /^[A-Za-z0-9_-]{1,64}$/;

/** `tit.paths.is_valid_name`: may `name` be one path component? */
export function isValidEntityName(name: string): boolean {
  return NAME_RE.test(name) && !name.includes("..");
}

/** `tit.catalog.is_safe_name`: may `name` be saved as a new catalog entry? */
export function isSafeName(name: string): boolean {
  return SAFE_NAME_RE.test(name);
}

/** The server's sentence for `NAME_RE` (`tit.paths.validate_name`), for a form's error line. */
export const ENTITY_NAME_RULE =
  "letters, digits, '.', '_', '-' and inner spaces only, not starting with '.', at most 128 characters";

/** The server's rule for a saved catalog entry (`tit.catalog.put_montage`, `put_freehand_config`). */
export const SAFE_NAME_RULE = "letters, digits, '_' and '-' only, at most 64 characters";

/** Why `name` cannot be saved as a catalog entry (`what` names it), or `null` when it can. */
export function safeNameProblem(name: string, what: string): string | null {
  return isSafeName(name) ? null : `A ${what} name may use ${SAFE_NAME_RULE}.`;
}

/** Why `name` cannot name a run folder (`what` names it), or `null` when it can. */
export function entityNameProblem(name: string, what: string): string | null {
  return isValidEntityName(name) ? null : `A ${what} name may use ${ENTITY_NAME_RULE}.`;
}
