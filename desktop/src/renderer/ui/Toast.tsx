import { useEffect, useState } from "react";
import { Toaster, toast } from "sonner";
import { ApiError, type MissingInput } from "../api/client";
import { Dialog } from "./Overlay";

/** Auto-dismiss for every toast, success or blocked; sonner already pauses this on hover. */
const TOAST_DURATION = 4000;

type MissingDialogState = { message: string; missing: readonly MissingInput[] } | null;

/**
 * `ToastHost` mounts once at the app root; `notify.blocked`'s "Details" action needs to open a
 * dialog from outside React (it runs from a sonner action callback, not a component), so it goes
 * through this module-level setter rather than context.
 */
let openMissingDialog: ((state: MissingDialogState) => void) | null = null;

/** Mount once at the app root. Every toast, including a blocked submission, self-dismisses. */
export function ToastHost() {
  const [missingDialog, setMissingDialog] = useState<MissingDialogState>(null);
  useEffect(() => {
    openMissingDialog = setMissingDialog;
    return () => {
      openMissingDialog = null;
    };
  }, []);

  return (
    <>
      <Toaster
        position="bottom-right"
        expand
        visibleToasts={4}
        // rb_13 #3: sits above the collapsed jobs rail — `.jobs-rail-collapsed` is 36px
        // (shell.css), plus 8px breathing room — which otherwise clips a second toast
        // (optimizer-ex-light.png) or sits on top of a rail trace (panel-source-dark.png).
        offset={44}
        toastOptions={{
          style: {
            background: "var(--surface)",
            color: "var(--ink)",
            border: "1px solid var(--line)",
            borderRadius: "var(--radius-card)",
            boxShadow: "var(--shadow-2)",
            fontSize: "13px",
            fontFamily: "var(--font-sans)",
          },
        }}
      />
      <Dialog
        open={missingDialog !== null}
        onOpenChange={(open) => {
          if (!open) setMissingDialog(null);
        }}
        title={missingDialog?.message ?? "Missing inputs"}
      >
        {missingDialog && (
          <ul className="missing-inputs-list">
            {missingDialog.missing.map((m, i) => (
              <li key={i}>
                <div className="missing-input-what">{m.what}</div>
                {m.expected_path && <code className="missing-input-path">{m.expected_path}</code>}
                <div className="missing-input-fix">{m.how_to_fix}</div>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
    </>
  );
}

export const notify = {
  success(message: string) {
    toast.success(message, { duration: TOAST_DURATION });
  },
  /** Persists until dismissed; pass `details` for a "Details" expandable action. */
  error(message: string, details?: string) {
    toast.error(message, {
      duration: Infinity,
      action: details
        ? {
            label: "Details",
            onClick: () => toast.message(details, { duration: 8000 }),
          }
        : undefined,
    });
  },
  info(message: string) {
    toast(message, { duration: TOAST_DURATION });
  },
  /**
   * A submission the server refused because inputs are missing (HTTP 422 "Missing inputs"):
   * a short toast (title + the first input's `what`, ellipsised) that self-dismisses like any
   * other toast, with a "Details" button that opens the full per-input list — what, expected
   * path, how to fix — in the shared `Dialog`.
   */
  blocked(message: string, missing: readonly MissingInput[]) {
    const first = missing[0];
    const id = toast.error(message, {
      duration: TOAST_DURATION,
      description: first ? <span className="toast-line-clamp">{first.what}</span> : undefined,
      action: {
        label: "Details",
        onClick: () => {
          toast.dismiss(id);
          openMissingDialog?.({ message, missing });
        },
      },
    });
  },
};

/** The notice for a failed submission: the missing-input list when the server sent one, else a plain error. */
export function notifySubmitError(message: string, error: unknown): void {
  const missing = error instanceof ApiError ? error.missing : undefined;
  if (missing?.length) {
    notify.blocked(`${message} Missing inputs:`, missing);
    return;
  }
  notify.error(message, error instanceof Error && error.message ? error.message : undefined);
}
