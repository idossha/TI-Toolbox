/**
 * Whether the *current window generation*'s quit has already been approved by
 * `handleQuitRequest` (the running-jobs prompt in `main/index.ts`).
 *
 * This used to be a single module-level `let allowQuit = false` in `index.ts` that
 * `handleQuitRequest` set to `true` and never reset (rb_12 NEW issue). On macOS closing a window
 * does not quit the app (it stays dock-resident, `window-all-closed` is a no-op there) —
 * `app.on("activate")` then creates a *new* window when the dock icon is clicked again. Because
 * the flag was never reset, that new window's own `close`/`before-quit` saw `allowQuit === true`
 * from the *first* window's approval and returned immediately, silently skipping the running-jobs
 * prompt for every session after the first. `index.ts` calls `reset()` every
 * time it creates a window (initial launch and `activate`), so each generation starts unapproved
 * regardless of what an earlier, now-closed window decided.
 *
 * Lives in `shared/`, not `main/`, purely so it can be unit-tested: it has no Electron/BrowserWindow
 * dependency (same reasoning as `shared/compose.ts` and `shared/paths.ts`), and `main/**` is outside
 * `tsconfig.web.json`'s project, which is what `tests/unit/**` type-checks under.
 */
export interface QuitGate {
  /** True once `approve()` has run for the current window generation. */
  isApproved(): boolean;
  /** Call once `handleQuitRequest` has finished its prompt/revert and is about to actually close. */
  approve(): void;
  /** Call whenever a new window generation starts (initial launch, or macOS `activate`). */
  reset(): void;
}

export function createQuitGate(): QuitGate {
  let approved = false;
  return {
    isApproved: () => approved,
    approve: () => {
      approved = true;
    },
    reset: () => {
      approved = false;
    },
  };
}
