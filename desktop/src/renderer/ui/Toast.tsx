import { Toaster, toast } from "sonner";

/** Mount once at the app root. Success toasts self-dismiss in 4s; errors stay until dismissed. */
export function ToastHost() {
  return (
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
  );
}

export const notify = {
  success(message: string) {
    toast.success(message, { duration: 4000 });
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
    toast(message, { duration: 4000 });
  },
};
