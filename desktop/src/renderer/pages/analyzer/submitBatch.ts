/**
 * Submitting one Run press's analyses, and saying honestly what happened.
 *
 * The Run button fans out into one `POST /api/jobs` per config (the analyzer has no single
 * server-side group call: `/api/jobs/groups` takes ONE config and plans it per subject, while
 * these are N different configs). `Promise.all` over that fan-out rejects on the first failure
 * (audit UI-05): the already-accepted jobs were never named, the page said "Could not queue the
 * analysis job(s)" as if nothing had run, and pressing Run again duplicated everything that had
 * in fact been accepted.
 *
 * So: settle them all, report both halves, and let the caller retry only the rejected specs.
 */

import { ApiError, type MissingInput } from "../../api/client";
import { isExistingOutputsConflict } from "../_shared/run/ExistingOutputsDialog";

export interface BatchOutcome<Spec> {
  /** Job ids the server accepted, in submission order. */
  acceptedIds: string[];
  /** The specs that were rejected, ready to be retried on their own. */
  rejected: { spec: Spec; message: string; missing?: MissingInput[]; error?: unknown }[];
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function missing(error: unknown): MissingInput[] | undefined {
  return error instanceof ApiError ? error.missing : undefined;
}

/** Submit every spec, waiting for all of them, whatever each one does. */
export async function submitBatch<Spec>(
  specs: readonly Spec[],
  submit: (spec: Spec) => Promise<{ id: string }>,
): Promise<BatchOutcome<Spec>> {
  const settled = await Promise.allSettled(specs.map((spec) => submit(spec)));
  const acceptedIds: string[] = [];
  const rejected: BatchOutcome<Spec>["rejected"] = [];
  settled.forEach((result, index) => {
    if (result.status === "fulfilled") acceptedIds.push(result.value.id);
    else rejected.push({ spec: specs[index] as Spec, message: message(result.reason), missing: missing(result.reason), error: result.reason });
  });
  return { acceptedIds, rejected };
}

/**
 * The sentence the user gets. A partial failure has to say both numbers — "2 of 3 queued" is the
 * only wording from which the right next action (retry the one) follows.
 */
export function batchReceipt<Spec>(outcome: BatchOutcome<Spec>, noun = "analysis", plural = "analyses"): string {
  const accepted = outcome.acceptedIds.length;
  const failed = outcome.rejected.length;
  const total = accepted + failed;
  if (failed === 0) return accepted === 1 ? `Queued: ${noun}` : `Queued: ${accepted} ${plural}`;
  if (accepted === 0) {
    // First line only: a refused submission's missing-input list is rendered as its own lines.
    const reason = outcome.rejected[0]?.message.split("\n")[0] ?? "";
    return total === 1 ? `Could not queue the ${noun}${reason ? `: ${reason}` : "."}` : `Could not queue any of the ${total} ${plural}.`;
  }
  return `Queued ${accepted} of ${total} ${plural}; ${failed} could not be queued — press Run again to retry just ${failed === 1 ? "it" : "them"}.`;
}

/**
 * Output already on disk is a question, not an error. The plan a Run press reads can lag the disk
 * (a run that just finished, a plan still resolving), so the refusals the server sent for existing
 * outputs are split off for the existing-outputs dialog; `reported` is what the receipt names.
 */
export function splitOutputConflicts<Spec>(outcome: BatchOutcome<Spec>): {
  conflicts: BatchOutcome<Spec>["rejected"];
  reported: BatchOutcome<Spec>;
} {
  const conflicts = outcome.rejected.filter((entry) => isExistingOutputsConflict(entry.error));
  return {
    conflicts,
    reported: { acceptedIds: outcome.acceptedIds, rejected: outcome.rejected.filter((entry) => !conflicts.includes(entry)) },
  };
}
