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
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { usePageSession } from "../../app/pageSession";
import type { ElectrodePosition } from "./api";
import { placeAt, removeAt, renumber } from "./freehandPlacement";

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
  /** One click on the scalp, in the drawn subject's own millimetres. */
  place: (world: readonly [number, number, number]) => void;
  remove: (index: number) => void;
  reset: () => void;
}

const Ctx = createContext<FreehandDraft | null>(null);

export function FreehandDraftProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = usePageSession("freehand.open", false);
  const [subject, setSubject] = usePageSession<string | undefined>("freehand.subject", undefined);
  const [name, setName] = usePageSession("freehand.name", "");
  const [positions, setPositions] = usePageSession<ElectrodePosition[]>("freehand.positions", initialPositions);

  const place = useCallback(
    (world: readonly [number, number, number]) => setPositions((prev) => placeAt(prev, world).positions),
    [setPositions],
  );
  const remove = useCallback((index: number) => setPositions((prev) => removeAt(prev, index)), [setPositions]);
  const reset = useCallback(() => {
    setName("");
    setPositions(initialPositions());
  }, [setName, setPositions]);

  const value = useMemo<FreehandDraft>(
    () => ({ open, setOpen, subject, setSubject, name, setName, positions, setPositions, place, remove, reset }),
    [open, setOpen, subject, setSubject, name, setName, positions, setPositions, place, remove, reset],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useFreehandDraft(): FreehandDraft {
  const value = useContext(Ctx);
  if (!value) throw new Error("useFreehandDraft outside <FreehandDraftProvider>");
  return value;
}
