/**
 * Each visited page owns its subject selection. The shell and palette project the active page's
 * selection; changing that selection cannot alter a hidden page's draft or reload its viewer.
 * First visits inherit the last active selection, ordinary navigation restores the destination's
 * selection, and an explicit subject deep link applies to that destination only.
 * `useSubject()` adds the catalog, batch selection and presence chips to the same scoped store.
 */
import { create } from "zustand";
import { useCallback, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, getSubjects, unwrap, type Subject } from "../api/client";
import { usePageId } from "./pageSession";

/** One presence fact about a subject: `raw`, `m2m`, `dwi`, … and whether it is there. */
export interface SubjectPresenceChip {
  label: string;
  on: boolean;
}

/** A subject plus its presence chips — what a picker row renders. */
export interface SubjectPickerItem {
  id: string;
  chips: SubjectPresenceChip[];
}

interface SubjectSelection {
  subjectId: string | null;
  /** Additional subjects for the multi-subject screens (Prepare, Simulate). Never includes `subjectId`. */
  batch: string[];
}

interface SubjectContextState extends SubjectSelection {
  activePage: string | null;
  pages: Record<string, SubjectSelection>;
  setSubject: (id: string | null) => void;
  setBatch: (ids: string[]) => void;
}

const useSubjectStore = create<SubjectContextState>((set) => ({
  subjectId: null,
  batch: [],
  activePage: null,
  pages: {},
  // Switching the primary subject drops it out of the batch if it was there: "ernie + 2 more"
  // must never mean "ernie + ernie + one other".
  setSubject: (id) => set((s) => {
    const selection = { subjectId: id, batch: id ? s.batch.filter((b) => b !== id) : s.batch };
    return { ...selection, pages: s.activePage ? { ...s.pages, [s.activePage]: selection } : s.pages };
  }),
  setBatch: (ids) => set((s) => {
    const selection = { subjectId: s.subjectId, batch: ids.filter((b) => b !== s.subjectId) };
    return { ...selection, pages: s.activePage ? { ...s.pages, [s.activePage]: selection } : s.pages };
  }),
}));

function changePageSelection(pageId: string, change: (selection: SubjectSelection) => SubjectSelection): void {
  useSubjectStore.setState((state) => {
    const selection = change(state.pages[pageId] ?? state);
    return {
      ...(state.activePage === pageId ? selection : {}),
      pages: { ...state.pages, [pageId]: selection },
    };
  });
}

/** The shell/palette see the active subject; a retained page sees only its own selection. */
export const useSubjectContext = Object.assign(
  function useSubjectContext<T>(selector: (state: SubjectContextState) => T): T {
    const pageId = usePageId();
    const setSubject = useCallback((id: string | null) => {
      changePageSelection(pageId, (selection) => ({
        subjectId: id,
        batch: id ? selection.batch.filter((other) => other !== id) : selection.batch,
      }));
    }, [pageId]);
    const setBatch = useCallback((ids: string[]) => {
      changePageSelection(pageId, (selection) => ({ ...selection, batch: ids.filter((id) => id !== selection.subjectId) }));
    }, [pageId]);
    return useSubjectStore((state) => selector(pageId
      ? { ...state, ...(state.pages[pageId] ?? state), setSubject, setBatch }
      : state));
  },
  useSubjectStore,
);

/** Plain navigation resumes a tab; an explicit subject deep link changes that destination. */
export function activateSubjectPage(pageId: string, linkedSubject?: string | null): void {
  useSubjectStore.setState((state) => {
    const previous = state.pages[pageId] ?? { subjectId: state.subjectId, batch: state.batch };
    const selection = linkedSubject
      ? { subjectId: linkedSubject, batch: previous.batch.filter((id) => id !== linkedSubject) }
      : previous;
    if (state.activePage === pageId && selection === previous && state.pages[pageId]) return state;
    return { ...selection, activePage: pageId, pages: { ...state.pages, [pageId]: selection } };
  });
}

export function clearSubjectPages(subjectId: string | null = null): void {
  useSubjectStore.setState({ subjectId, batch: [], activePage: null, pages: {} });
}

// ---------------------------------------------------------------------------
// Persistence: per project, so opening a different dataset does not resume a
// subject that does not exist in it.
// ---------------------------------------------------------------------------

const STORAGE_PREFIX = "tit-subject:";

export function readStoredSubject(project: string): string | null {
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + project);
  } catch {
    // localStorage unavailable (private mode, sandboxed webview) — no remembered subject.
    return null;
  }
}

export function writeStoredSubject(project: string, id: string | null): void {
  try {
    if (id) window.localStorage.setItem(STORAGE_PREFIX + project, id);
    else window.localStorage.removeItem(STORAGE_PREFIX + project);
  } catch {
    // best-effort mirror only
  }
}

// ---------------------------------------------------------------------------
// The v2 hook
// ---------------------------------------------------------------------------

/** `raw`/`fastsurfer`/`freesurfer`/`m2m` come with the list; `dwi`/`ct` need the per-subject detail. */
export type SubjectDetail = Subject & { has_dwi: boolean; has_ct: boolean; has_leadfields: string[] };

export async function getSubjectDetail(id: string): Promise<SubjectDetail> {
  return unwrap(
    await api.GET("/api/catalog/subjects/{id}", { params: { path: { id } } }),
    "/api/catalog/subjects/{id}",
  ) as SubjectDetail;
}

/** The presence-chip vocabulary, shared by the switcher, the batch picker and the Project table. */
export function presenceChips(subject: Subject | SubjectDetail | undefined): SubjectPresenceChip[] {
  if (!subject) return [];
  const chips: SubjectPresenceChip[] = [
    { label: "raw", on: subject.has_raw },
    // FastSurfer before FreeSurfer, matching `tit/catalog.py`'s own column order: FastSurfer is
    // what v3 runs (D2) and FreeSurfer is the legacy derivative it accepts, so the newer one reads
    // first. Both are shown — a subject can have either, both or neither, and "which segmentation
    // do I actually have" is the question these chips exist to answer.
    { label: "fastsurfer", on: subject.has_fastsurfer },
    { label: "freesurfer", on: subject.has_freesurfer },
    { label: "m2m", on: subject.has_m2m },
  ];
  if ("has_dwi" in subject) chips.push({ label: "dwi", on: subject.has_dwi }, { label: "ct", on: subject.has_ct });
  return chips;
}

export interface UseSubject {
  /** The primary subject. `null` until one is chosen — pages show "No subject", never a guess. */
  id: string | null;
  setId: (id: string | null) => void;
  /** Additional subjects for batch screens. Excludes `id`. */
  batch: string[];
  setBatch: (ids: string[]) => void;
  /** `id` first, then the batch — what a batch screen actually submits. */
  selection: string[];
  /** The project's subjects, from the same `["subjects"]` query the Project page uses. */
  subjects: Subject[];
  subjectsPending: boolean;
  /** Presence chips for the current subject (with dwi/ct once the detail lands). */
  chips: SubjectPresenceChip[];
  /** A subject plus its presence chips, for anything that lists subjects. */
  items: SubjectPickerItem[];
}

export function useSubject(): UseSubject {
  const id = useSubjectContext((s) => s.subjectId);
  const setId = useSubjectContext((s) => s.setSubject);
  const batch = useSubjectContext((s) => s.batch);
  const setBatch = useSubjectContext((s) => s.setBatch);

  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  // One extra request, for the selected subject only: dwi/ct live on SubjectDetail, not on the
  // list row, and the crumb is the one place those two chips are worth a round trip.
  const detailQuery = useQuery({
    queryKey: ["subject-detail", id],
    queryFn: () => getSubjectDetail(id as string),
    enabled: id !== null,
  });

  const subjects = useMemo(() => subjectsQuery.data ?? [], [subjectsQuery.data]);
  const listed = useMemo(() => subjects.find((s) => s.id === id), [subjects, id]);

  return {
    id,
    setId,
    batch,
    setBatch,
    selection: useMemo(() => (id ? [id, ...batch] : batch), [id, batch]),
    subjects,
    subjectsPending: subjectsQuery.isPending,
    chips: presenceChips(detailQuery.data ?? listed),
    items: useMemo(() => subjects.map((s) => ({ id: s.id, chips: presenceChips(s) })), [subjects]),
  };
}

/**
 * Keeps a page's own subject value and its subject context in step, in both directions.
 * Stage-2 pages drop this in beside their existing state and delete their picker; a page that
 * still owns a picker (every page today) can adopt it one screen at a time.
 *
 * Only the calling page's context is read: a hidden page must never adopt a subject chosen in
 * another tab.
 */
export function useSubjectSync(pageValue: string | null, setPageValue: (id: string) => void): void {
  const id = useSubjectContext((s) => s.subjectId);
  const setSubject = useSubjectContext((s) => s.setSubject);

  useEffect(() => {
    if (id && id !== pageValue) setPageValue(id);
    else if (!id && pageValue) setSubject(pageValue);
    // `setPageValue` is a page-owned callback; depending on it would re-run this on every render
    // of a page that builds it inline, which is most of them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, pageValue, setSubject]);
}
