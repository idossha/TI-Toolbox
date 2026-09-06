/**
 * **Where the user scrolled the work pane, kept for the session** (lane N2).
 *
 * The failure it prevents: on a run page tall enough to scroll (the Optimizer at 1280×800 is
 * 55 px past its scrollport with Flex selected), scrolling down to a section, stepping onto
 * Results and coming back put the page back at the top — measured as `scrollTop 55 → 0` by
 * `tests/e2e/page-memory.spec.ts` before this existed.
 *
 * Restoring an offset is not one assignment. The page mounts short — the plan is still resolving,
 * the subject table has not measured its ground rows, `RunWork`'s fill controller has not opened
 * anything yet — so `el.scrollTop = 55` is clamped to whatever the content allows at that instant
 * and the browser keeps the clamp. The offset is therefore re-applied on every content resize
 * until it lands, and abandoned when it cannot land:
 *
 *  - it stops the moment `scrollTop` equals the target (the content has grown enough);
 *  - it stops at `RESTORE_MS`, so a page whose content never gets that tall does not keep yanking
 *    the view down while the user reads it;
 *  - it stops immediately on a `wheel`, a `touchstart` or a `keydown` in the pane — a user who
 *    scrolls during the restore window has just made a newer decision than the stored one, and the
 *    stored offset must not fight them.
 *
 * Recording is suspended while restoring, for the reason above: the clamped intermediate values
 * are the browser's, not the user's, and writing one back would overwrite the offset being
 * restored with a 0.
 */

/** How long a restore keeps trying before it gives up. Two seconds is longer than any measured
 *  first paint of a run page (§S8 budgets a warm pane at ≤ 2.5 s, cold ≤ 12 s, but the *content*
 *  height is settled long before the scene inside the right pane is). */
const RESTORE_MS = 2000;

export interface ScrollMemory {
  /** Call whenever the pane's content height may have changed. */
  retry(): void;
  /** Detach every listener. */
  dispose(): void;
}

/**
 * Attaches scroll memory to one scroll container.
 *
 * `read`/`write` are the session bag's (`app/pageSession.ts`), passed in rather than imported so
 * this module stays a pure function of its inputs and can be driven by a test.
 */
export function attachScrollMemory(
  scroller: HTMLElement,
  read: () => number | undefined,
  write: (value: number) => void,
  now: () => number = () => Date.now(),
): ScrollMemory {
  const target = read() ?? 0;
  const deadline = now() + RESTORE_MS;
  let restoring = target > 0;

  const stop = (): void => {
    restoring = false;
  };

  const apply = (): void => {
    if (!restoring) return;
    if (now() > deadline) {
      restoring = false;
      return;
    }
    scroller.scrollTop = target;
    // Landed: the content is finally tall enough, so this becomes the user's own offset again.
    if (Math.abs(scroller.scrollTop - target) < 1) restoring = false;
  };

  const onScroll = (): void => {
    // While restoring, every value is the browser's clamp of an offset we are still trying to
    // reach; writing one back would erase the target with a 0.
    if (restoring) return;
    write(Math.round(scroller.scrollTop));
  };

  scroller.addEventListener("scroll", onScroll, { passive: true });
  scroller.addEventListener("wheel", stop, { passive: true });
  scroller.addEventListener("touchstart", stop, { passive: true });
  scroller.addEventListener("keydown", stop);
  apply();

  return {
    retry: apply,
    dispose() {
      scroller.removeEventListener("scroll", onScroll);
      scroller.removeEventListener("wheel", stop);
      scroller.removeEventListener("touchstart", stop);
      scroller.removeEventListener("keydown", stop);
    },
  };
}
