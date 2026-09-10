/**
 * The free-hand placement draft, held once for the whole Simulator page.
 *
 * It used to live in two places — `MontageManager` owned "is the editor open", `FreehandEditor`
 * owned the rows — and both were `usePageSession` slots, whose contract is *"the owner of a slot
 * is exactly one component"*. That was fine while the editor was the only thing that could read or
 * write a position. It stopped being fine when the 3-D pane became a way to *enter* one: the pane
 * is rendered by `pages/simulator/index.tsx`, three levels above the editor, so a click on the
 * scalp and a number typed into the table have to reach the same array.
 *
 * Hence one provider at the page root and one hook. The slots keep their old keys, so a draft left
 * open before this change comes back exactly as it was.
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { usePageSession } from "../../app/pageSession";
import type { ElectrodePosition } from "./api";
import { POSITIONS_PER_STEP, placeAt, removeAt, renumber } from "./freehandPlacement";

/**
 * Four blank rows — the editor's own "4 positions = 2 pairs, standard TI" starting point — already
 * named `E1+ E1− E2+ E2−`, so the empty table states the plan before anything is clicked.
 */
const EMPTY_POSITION: ElectrodePosition = { label: "", x: 0, y: 0, z: 0 };
export const initialPositions = (): ElectrodePosition[] =>
  renumber([{ ...EMPTY_POSITION }, { ...EMPTY_POSITION }, { ...EMPTY_POSITION }, { ...EMPTY_POSITION }]);

export interface FreehandDraft {
  open: boolean;
  setOpen: (open: boolean) => void;
  /** The subject the placement is FOR — and therefore the head the pane must draw. */
  subject: string | undefined;
  setSubject: (subject: string | undefined) => void;
  name: string;
  setName: (name: string) => void;
  positions: ElectrodePosition[];
  setPositions: (next: ElectrodePosition[] | ((prev: ElectrodePosition[]) => ElectrodePosition[])) => void;
  /**
   * The one row a click on the scalp writes into, or `null` for "none selected, so a click does
   * nothing". Selection comes first and never moves by itself (maintainer, 2026-09-06) — "which
   * electrode am I manipulating" is the question the whole gesture turns on, and a mode where the
   * answer is "whichever row was empty" makes the user read the table to find out what happened.
   */
  active: number | null;
  setActive: (index: number | null) => void;
  /** One click on the scalp, in the drawn subject's own millimetres: writes the active row. */
  place: (world: readonly [number, number, number]) => void;
  /** Adds one pair of rows and makes the first of them active. */
  add: () => void;
  remove: (index: number) => void;
  reset: () => void;
  /** The row the cursor is over — in the table or on the scalp; the other end highlights. */
  hovered: number | null;
  setHovered: (index: number | null) => void;
}

const Ctx = createContext<FreehandDraft | null>(null);

export function FreehandDraftProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = usePageSession("freehand.open", false);
  const [subject, setSubject] = usePageSession<string | undefined>("freehand.subject", undefined);
  const [name, setName] = usePageSession("freehand.name", "");
  const [positions, setPositions] = usePageSession<ElectrodePosition[]>("freehand.positions", initialPositions);
  const [active, setActive] = usePageSession<number | null>("freehand.active", null);
  // Not page-session state: a hover is where the cursor is right now, and restoring one on the next
  // visit would light up a row nobody is pointing at.
  const [hovered, setHovered] = useState<number | null>(null);

  const place = useCallback(
    (world: readonly [number, number, number]) => {
      const result = placeAt(positions, world, active);
      // Nothing selected: the click is refused, and the pane's hint is what says so.
      if (result.index < 0) return;
      setPositions(result.positions);
      // The selection deliberately stays put, so a second click MOVES this electrode.
    },
    [positions, active, setPositions],
  );
  const add = useCallback(() => {
    setPositions((prev) => renumber([...prev, ...Array.from({ length: POSITIONS_PER_STEP }, () => ({ ...EMPTY_POSITION }))]));
    setActive(positions.length);
  }, [positions.length, setPositions, setActive]);
  const remove = useCallback(
    (index: number) => {
      setPositions((prev) => removeAt(prev, index));
      // Back to nothing selected: the row the user was pointing at is gone, and silently moving the
      // aim to its neighbour would place the next click on an electrode nobody chose.
      setActive(null);
    },
    [setPositions, setActive],
  );
  const reset = useCallback(() => {
    setName("");
    setPositions(initialPositions());
    setActive(null);
  }, [setName, setPositions, setActive]);

  // A selection can be left pointing past the end (a row removed elsewhere). Corrected during
  // render rather than in an effect: an effect paints one frame naming a row that is not there.
  const [lastCount, setLastCount] = useState(positions.length);
  if (positions.length !== lastCount) {
    setLastCount(positions.length);
    if (active !== null && active >= positions.length) setActive(null);
  }

  const value = useMemo<FreehandDraft>(
    () => ({
      open, setOpen, subject, setSubject, name, setName, positions, setPositions,
      active, setActive, place, add, remove, reset, hovered, setHovered,
    }),
    [open, setOpen, subject, setSubject, name, setName, positions, setPositions, active, setActive, place, add, remove, reset, hovered],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useFreehandDraft(): FreehandDraft {
  const value = useContext(Ctx);
  if (!value) throw new Error("useFreehandDraft outside <FreehandDraftProvider>");
  return value;
}
