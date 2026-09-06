/**
 * Maps `/api/validate/{kind}` and job-submission error bodies (`{ok, errors: [{path, message}]}`,
 * plan §3) onto react-hook-form fields. `path` is dot/bracket JSON-pointer-ish
 * ("montage.pairs.0.electrode"); react-hook-form accepts the same dot+index syntax as a field
 * name, so most paths need no translation — this only normalises a leading "/" or "#/" a
 * JSON-Pointer-flavoured backend might send.
 */
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

export interface FieldValidationError {
  path: string;
  message: string;
}

export function normalizeErrorPath(path: string): string {
  return path.replace(/^#?\//, "").replace(/\//g, ".").replace(/^\.+/, "");
}

/** Apply every server-reported field error to a react-hook-form instance via `setError`. */
export function applyServerErrors<T extends FieldValues>(
  setError: UseFormSetError<T>,
  errors: FieldValidationError[],
): void {
  for (const err of errors) {
    const path = normalizeErrorPath(err.path);
    if (!path) continue; // form-level error (no field): the Plan panel shows it, not a field
    setError(path as Path<T>, { type: "server", message: err.message });
  }
}

/** Errors with an empty/root path — surfaced by the Plan panel rather than attached to a field. */
export function formLevelErrors(errors: FieldValidationError[]): string[] {
  return errors.filter((e) => !normalizeErrorPath(e.path)).map((e) => e.message);
}
