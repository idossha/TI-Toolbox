/**
 * The one existing-outputs decision, for all four run pages (plan §1-C, C3).
 *
 * 2.5.0 asked the question once, in one wording, with three answers: **Skip** the jobs whose output
 * is already there, **Replace** them, or **Cancel**. v3 had grown four different versions of it —
 * the Simulator a two-button "Overwrite existing simulation outputs?", Pre-processing a "Replace
 * existing outputs?" gated behind a segmented control the user had to have set first, the Optimizer
 * a bare `confirm`-shaped alert, the Analyzer none at all — and two of them offered no way to run
 * the *rest* of the batch, which is the answer people actually want: run the four that are new and
 * leave the two that are done.
 *
 * So it is one component, and Skip is the default (the safe answer, and the one that makes a
 * re-pressed Run finish a partly-completed batch). `onDecide` hands the page a policy rather than a
 * boolean, so the page's own submit call keeps deciding what "replace" means for its job kind.
 */
import { Button } from "../../../ui/Button";
import { Dialog } from "../../../ui/Overlay";

export type ExistingOutputsDecision = "skip" | "replace";

export function ExistingOutputsDialog({
  open,
  onOpenChange,
  /** How many of the planned jobs already have output. */
  existing,
  /** How many jobs the batch has in total — "2 of 6" is the sentence that makes the choice easy. */
  total,
  /** "simulation", "optimization", "analysis", "pre-processing" — what the outputs are. */
  noun = "output",
  onDecide,
  busy,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existing: number;
  total: number;
  noun?: string;
  onDecide: (decision: ExistingOutputsDecision) => void;
  busy?: boolean;
}) {
  const rest = Math.max(0, total - existing);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Some outputs already exist"
      description={
        `${existing} of ${total} planned job${total === 1 ? "" : "s"} already ${existing === 1 ? "has" : "have"} ` +
        `${noun} on disk.` +
        (rest > 0 ? ` The other ${rest} ${rest === 1 ? "job" : "jobs"} will run either way.` : "")
      }
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} data-testid="existing-outputs-cancel">
            Cancel
          </Button>
          <Button variant="secondary" loading={busy} onClick={() => onDecide("replace")} data-testid="existing-outputs-replace">
            Replace and rerun
          </Button>
          {/* The default: it is the safe answer, and it is what finishes a partly-completed batch. */}
          <Button variant="primary" loading={busy} onClick={() => onDecide("skip")} data-testid="existing-outputs-skip">
            {rest > 0 ? `Skip ${existing}, run ${rest}` : "Skip them"}
          </Button>
        </>
      }
    >
      <p className="field-help" data-testid="existing-outputs-detail">
        Skipping leaves the existing {noun} untouched. Replacing overwrites {existing === 1 ? "it" : "them"}; this cannot be
        undone.
      </p>
    </Dialog>
  );
}
