/**
 * The run pages' work pane and its **fill rule** (fix lane FXU1, program U1).
 *
 * The failure it prevents, measured on the merged tree: Simulator at 1440×900 was ~65 % empty
 * because three collapsed-by-default sections left a 340 px form in a 760 px pane. Collapsing by
 * default is right when the content would overflow and wrong when it would not — so the decision
 * is made by measurement, once on mount and again whenever the pane resizes, instead of by a
 * `defaultOpen={false}` written when nobody knew how tall the pane would be.
 *
 * The algorithm, deliberately boring:
 *   1. read the scroll container's `clientHeight` and `scrollHeight`;
 *   2. slack (nothing overflows and ≥ `SLACK` px are free) → open the first still-closed section
 *      the controller is allowed to touch, shallowest tier first, and measure again next frame;
 *   3. overflow → close the last section the controller opened, deepest tier first;
 *   4. stop when neither applies, or after `MAX_PASSES` (a section whose own height changes with
 *      its open state can otherwise oscillate).
 *
 * It never touches a section the user has toggled by hand, and never closes one the density rule
 * pinned open (`changed`/`error`) — both are enforced in `FormSection` itself, not here.
 *
 * **A user-touched section outranks everything, for the whole session** (lane N2, the maintainer's
 * report "the state of the tabs is not persistent: jumping between tabs resets them"). A page
 * unmounts on every navigation, so before this the controller's memory of what the user had
 * decided died with it and the next mount re-derived the layout from scratch — Simulator's
 * `Electrodes` and `Conductivity` came back open after the user closed them, the Optimizer's
 * "After the search" came back closed after they opened it. Both halves of the controller's state
 * now live in the page's session bag (`app/pageSession.ts`): the user's own decisions, which
 * nothing may overrule, and the controller's own opened set, so the layout a page comes back to is
 * the layout it was left in rather than whatever this mount happens to measure first.
 *
 * That also settles the arbitration lane CL2 flagged (`cl2-notes.md` §8.2) between this controller
 * and `SubjectsField`'s `fill` table, which claim the same slack and were ordered only by which
 * measured first. The rule is written here and enforced in both places: **the user's own sections
 * are not slack.** This controller never opens or closes one of them (the `userOpen` filter
 * below), and the table re-measures its ground rows against the column whenever a section opens,
 * giving room back instead of taking it — its `others` term is invariant to its own height, so
 * that cannot oscillate.
 *
 * **Content growth is a new question too** (lane LAY, fixing lane UC's second finding). Round 1
 * observed only the pane, so a page whose content grew *after* mount kept whatever answer it had
 * from a pane that was then a different size: the Analyzer's `ResultsPanel` gains rows the moment a
 * simulation is chosen, and the sections stayed open over the top of it. The observer now watches
 * the content as well — with two rules that make the loop provably convergent rather than a
 * flip-flop, which is the failure UC actually measured ("oscillated it open/closed live"):
 *   a. a change the controller caused itself is not a new question (`selfChange`),
 *   b. a section the rule closed to give height back is not re-opened until the *pane* resizes
 *      (`closedByOverflow`). Between two pane sizes the decision is therefore monotone — sections
 *      can only close — so open→close→open cannot cycle however the content moves, and
 *   c. a section under the pointer is not a candidate. That closes N2's open click race: if a
 *      person aims at a collapsed header while the mount-time fill pass is still settling, the
 *      controller must not open it first and turn the intended open-click into a close-click.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { FormSectionFillContext, type FormSectionFill } from "../../../ui/Layout";
import { usePageSession, usePageSessionRef } from "../../../app/pageSession";
import { usePageActive } from "../../../app/pageActivity";
import { attachScrollMemory } from "./scrollMemory";
import "./run.css";

/** Free pixels below which opening one more section is not worth the reflow. */
const SLACK = 96;
/** Bounded so a pathological layout cannot spin the measure loop. */
const MAX_PASSES = 12;
/** First-paint grace: a section must not auto-open between a user's aim and click. */
const INITIAL_POINTER_GUARD_MS = 240;
/** Extended whenever the pointer is inside the form, so the controller does not rearrange under it. */
const POINTER_GUARD_MS = 700;

function clockNow(): number {
  return typeof performance === "undefined" ? Date.now() : performance.now();
}

function hasHoveredSection(root: HTMLElement): boolean {
  try {
    return root.querySelector("[data-fill-section]:hover") !== null;
  } catch {
    return false;
  }
}

interface Registered {
  pinned: boolean;
}

/** The work pane this `.run-work` lives in — the box whose height the fill rule is measured in. */
function paneOf(root: HTMLElement): HTMLElement | null {
  return root.closest<HTMLElement>('[data-testid="page-work"]');
}

/**
 * Height available to the sections: the work pane minus its action bar.
 *
 * Not `scrollHeight` and not the scroll child's `scrollHeight` — both are `max(content, box)` and
 * so report zero slack exactly when there IS slack, which is the measurement bug round 1 shipped
 * with (Simulator stayed 55 % empty because the controller believed the pane was full).
 *
 * Since L4 the scrollport IS the box the sections have to fit in — the action bar is a sibling
 * outside it — so the scroll child's `clientHeight` is the honest number and needs no subtraction.
 * The `.action-bar` branch is the fallback for a layout that has not been migrated (and for jsdom,
 * where `clientHeight` is 0).
 */
function availableHeight(work: HTMLElement): number {
  const scroller = work.querySelector<HTMLElement>("[data-page-work-scroll]");
  if (scroller && scroller.clientHeight > 0) return scroller.clientHeight;
  const bar = work.querySelector<HTMLElement>(".action-bar");
  return work.clientHeight - (bar?.offsetHeight ?? 0);
}

export interface RunWorkProps {
  children: ReactNode;
  /**
   * Off for a page that has already sized its own sections (the Optimizer keeps its density).
   *
   * It turns off the **measuring** only. The section memory below is not part of the fill rule —
   * it is the user's own state — and switching it off with the measurement is the bug lane N2
   * measured on the Optimizer: `fill={false}` handed `FormSection` a null context, so a section the
   * user closed was never recorded and `defaultOpen` decided again on the next mount. Electrodes
   * came back open after being closed and "After the search" came back closed after being opened.
   */
  fill?: boolean;
  className?: string;
}

export function RunWork({ children, fill = true, className }: RunWorkProps) {
  const active = usePageActive();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const registry = useRef(new Map<string, Registered>());
  /** The user's own decisions, section id -> open. Session-scoped, per page (N2). */
  const [userOpen, setUserOpen] = usePageSession<Record<string, boolean>>("sections.user", {});
  /** The controller's own opened set, likewise per page, so a return visit starts where it left. */
  const [openList, setOpenList] = usePageSession<string[]>("sections.controller", []);
  const openIds = useMemo<ReadonlySet<string>>(() => new Set(openList), [openList]);
  const setOpenIds = useCallback(
    (next: (prev: ReadonlySet<string>) => ReadonlySet<string>) => {
      setOpenList((prev) => Array.from(next(new Set(prev))));
    },
    [setOpenList],
  );
  const scrollBag = usePageSessionRef<number>("workScroll");
  const passes = useRef(0);
  const [tick, setTick] = useState(0);
  /** Sections the rule closed to give height back. Not re-opened until the pane resizes (rule b). */
  const closedByOverflow = useRef(new Set<string>());
  /** True while the next content resize is one this controller caused (rule a). */
  const selfChange = useRef(false);
  /** The content height the last measure saw, so a resize callback can tell a real change. */
  const lastContentH = useRef(0);
  /** While true, a person is close enough to click; the controller must not move targets. */
  const controllerPausedUntil = useRef(clockNow() + INITIAL_POINTER_GUARD_MS);
  const pauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleAfterPause = useCallback(() => {
    if (pauseTimer.current) clearTimeout(pauseTimer.current);
    const delay = Math.max(0, controllerPausedUntil.current - clockNow()) + 16;
    pauseTimer.current = setTimeout(() => {
      passes.current = 0;
      setTick((t) => t + 1);
    }, delay);
  }, []);
  const pauseController = useCallback(
    (ms: number) => {
      controllerPausedUntil.current = Math.max(controllerPausedUntil.current, clockNow() + ms);
      scheduleAfterPause();
    },
    [scheduleAfterPause],
  );

  const register = useCallback((id: string, pinned: boolean) => {
    registry.current.set(id, { pinned });
  }, []);
  const onUserToggle = useCallback(
    (id: string, open: boolean) => {
      setUserOpen((prev) => (prev[id] === open ? prev : { ...prev, [id]: open }));
    },
    [setUserOpen],
  );
  // `fill={false}` means the controller has no opinion about any section — not that the user's own
  // decisions stop being recorded (see `RunWorkProps.fill`).
  const openFor = useCallback((id: string) => (fill && openIds.has(id) ? true : undefined), [fill, openIds]);
  const userOpenFor = useCallback((id: string) => userOpen[id], [userOpen]);

  const context = useMemo<FormSectionFill>(
    () => ({ openFor, userOpenFor, register, onUserToggle }),
    [openFor, userOpenFor, register, onUserToggle],
  );

  // The fill rule is allowed to derive an untouched layout, not to move a target under a pointer.
  // A page can mount under the user's cursor after a nav click; without the first-paint pause the
  // controller could open a section one frame before the click lands, turning an intended "open"
  // into a sticky "closed" decision. Pointer activity keeps the pause alive; if the user leaves it
  // alone, the scheduled tick below lets the controller fill the slack as before.
  useEffect(() => {
    if (!fill || !active) return;
    scheduleAfterPause();
    return () => {
      if (pauseTimer.current) clearTimeout(pauseTimer.current);
    };
  }, [active, fill, scheduleAfterPause]);

  useEffect(() => {
    if (!fill || !active) return;
    const root = rootRef.current;
    if (!root) return;
    const pause = () => pauseController(POINTER_GUARD_MS);
    root.addEventListener("pointerover", pause, { passive: true });
    root.addEventListener("pointermove", pause, { passive: true });
    root.addEventListener("pointerdown", pause, { capture: true, passive: true });
    return () => {
      root.removeEventListener("pointerover", pause);
      root.removeEventListener("pointermove", pause);
      root.removeEventListener("pointerdown", pause, { capture: true });
    };
  }, [active, fill, pauseController]);

  // Re-measure on mount, on every pass, and whenever the pane or its content resizes.
  useEffect(() => {
    if (!fill || !active) return;
    const root = rootRef.current;
    if (!root) return;
    const work = paneOf(root);
    if (!work) return;

    let frame = 0;
    const measure = () => {
      if (passes.current >= MAX_PASSES) return;
      if (clockNow() < controllerPausedUntil.current) return;
      if (hasHoveredSection(root)) {
        pauseController(POINTER_GUARD_MS);
        return;
      }
      // `scroller.scrollHeight` is `max(content, padding box)`, so it can never report SLACK —
      // it equals `clientHeight` the moment the content is shorter than the pane. The content's
      // own height is the honest number, and `.run-work` is an auto-height flex column, so its
      // border box IS the content height.
      const contentHeight = root.getBoundingClientRect().height;
      lastContentH.current = contentHeight;
      const free = availableHeight(work) - contentHeight;
      const overflow = -free;
      // DOM order, so "shallowest first" is simply "first in the document".
      const sections = Array.from(root.querySelectorAll<HTMLElement>("[data-fill-section][data-fill-collapsible]"));
      const underPointer = (el: HTMLElement): boolean => el.matches(":hover") || el.querySelector(":hover") !== null;
      const candidates = sections.filter((el) => {
        const id = el.dataset.fillSection ?? "";
        // A section the user has touched — in this mount or an earlier one this session — is not
        // slack, and is not the controller's to give away (N2). A section under the pointer is
        // also not slack: the next click belongs to the person, not to this frame's fill pass.
        return id && !(id in userOpen) && !registry.current.get(id)?.pinned && !underPointer(el);
      });

      if (free >= SLACK) {
        const next = candidates.find((el) => {
          const id = el.dataset.fillSection ?? "";
          return !openIds.has(id) && !closedByOverflow.current.has(id);
        });
        if (next) {
          passes.current += 1;
          const id = next.dataset.fillSection as string;
          selfChange.current = true;
          setOpenIds((prev) => new Set([...prev, id]));
          return;
        }
      }
      if (overflow > 0 && openIds.size > 0) {
        // Deepest tier first, then last in document order: the section furthest from the user's
        // primary decision is the one that gives its height back.
        const opened = candidates.filter((el) => openIds.has(el.dataset.fillSection ?? ""));
        const victim = [...opened].sort((a, b) => Number(b.dataset.fillTier ?? 2) - Number(a.dataset.fillTier ?? 2)).pop();
        if (victim) {
          passes.current += 1;
          const id = victim.dataset.fillSection as string;
          selfChange.current = true;
          closedByOverflow.current.add(id);
          setOpenIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
        }
      }
    };

    frame = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(frame);
  }, [active, fill, openIds, pauseController, setOpenIds, userOpen, tick]);

  // A pane resize is a new question, so the pass budget resets with it — and so does the
  // "closed to give height back" set, because at a different pane size that answer was for a
  // different question.
  useEffect(() => {
    if (!fill || !active) return;
    const root = rootRef.current;
    if (!root || typeof ResizeObserver === "undefined") return;
    const work = paneOf(root);
    if (!work) return;
    let last = { w: 0, h: 0 };
    const ro = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (!box) return;
      if (Math.abs(box.width - last.w) < 2 && Math.abs(box.height - last.h) < 2) return;
      last = { w: box.width, h: box.height };
      closedByOverflow.current.clear();
      passes.current = 0;
      setTick((t) => t + 1);
    });
    ro.observe(work);
    return () => ro.disconnect();
  }, [active, fill]);

  // Content that grows on its own is a new question as well (lane UC's second finding): the
  // Analyzer's results table gains rows when a simulation is chosen, and before this the sections
  // kept the answer they had computed against a page that no longer existed. `selfChange` keeps
  // the controller's own reflow out of it, and `closedByOverflow` (cleared only on a pane resize)
  // makes what follows monotone, so this cannot become the flip-flop UC measured.
  useEffect(() => {
    if (!fill || !active) return;
    const root = rootRef.current;
    if (!root || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      const h = root.getBoundingClientRect().height;
      if (Math.abs(h - lastContentH.current) < 2) return;
      lastContentH.current = h;
      if (selfChange.current) {
        // The measure pass that caused this is already scheduled by the `openIds` effect.
        selfChange.current = false;
        return;
      }
      passes.current = 0;
      setTick((t) => t + 1);
    });
    ro.observe(root);
    return () => ro.disconnect();
  }, [active, fill]);

  // Where the user scrolled this page's work pane (N2, `scrollMemory.ts`). Independent of `fill`:
  // a page that sizes its own sections still scrolls, and still has to come back where it was.
  // The offset is re-applied on every content resize because the page mounts short — the plan is
  // still resolving and the sections have not opened yet — so the first assignment is clamped.
  const scrollRead = scrollBag.read;
  const scrollWrite = scrollBag.write;
  useEffect(() => {
    if (!active) return;
    const root = rootRef.current;
    if (!root) return;
    const scroller = root.closest<HTMLElement>("[data-page-work-scroll]");
    if (!scroller) return;
    const memory = attachScrollMemory(scroller, scrollRead, scrollWrite);
    if (typeof ResizeObserver === "undefined") return () => memory.dispose();
    const ro = new ResizeObserver(() => memory.retry());
    ro.observe(root);
    return () => {
      ro.disconnect();
      memory.dispose();
    };
  }, [active, scrollRead, scrollWrite]);

  return (
    <FormSectionFillContext.Provider value={context}>
      <div className={className ? `run-work ${className}` : "run-work"} data-testid="run-work" ref={rootRef}>
        {children}
      </div>
    </FormSectionFillContext.Provider>
  );
}
