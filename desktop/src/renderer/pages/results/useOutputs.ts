/**
 * The catalog reads behind the Results outputs tree.
 *
 * It fed the Subjects page's output counts too until R1 (`desktop/IMPLEMENTATION_PLAN.md`) made
 * that page the Overview and gave it one aggregate endpoint: a project-wide *count* must not be a
 * per-subject fan-out, because the cap below silently blanked it above 25 subjects. Results is the
 * one caller now, and here the laziness is the design — this module builds the detailed **tree**
 * for the subject the user has open, not a project-wide number.
 *
 * **Fan-out budget.** Per subject: simulations, flex, ex, mex, reports (5), plus one analyses call
 * per simulation. That is cheap for a handful of subjects and rude for a hundred, so the eager
 * fetch is capped at `EAGER_SUBJECT_LIMIT`; past it only the selected subject is loaded and the
 * other rows omit their count instead of printing a `0` nobody measured.
 */
import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  getAnalyses,
  getExRuns,
  getFlexRuns,
  getGroupCatalog,
  getReports,
  getSimulationsFor,
  type Analysis,
  type ExRun,
  type FlexRun,
  type Report,
  type SimulationDetail,
} from "./api";
import { GROUP_SUBJECT, groupOutputsFor, outputsTreeFor, type SubjectOutputs } from "./outputsTree";

/**
 * Above this many subjects, only the selected one's outputs are fetched. Since R1 this only ever
 * withholds detail from an unselected row of the Results browser — no page renders a project-wide
 * count from these reads any more.
 */
export const EAGER_SUBJECT_LIMIT = 25;

interface SubjectQueries {
  simulations: SimulationDetail[] | undefined;
  flexRuns: FlexRun[] | undefined;
  exRuns: ExRun[] | undefined;
  mexRuns: ExRun[] | undefined;
  reports: Report[] | undefined;
}

export interface OutputsState {
  /** Keyed by subject id; `undefined` while that subject's queries are in flight or not requested. */
  bySubject: Record<string, SubjectOutputs | undefined>;
  /** The `Group` pseudo-subject, or `undefined` until the group catalog lands. */
  group: SubjectOutputs | undefined;
  /** True while any query this hook owns is still fetching for the first time. */
  pending: boolean;
}

/**
 * Every subject's outputs plus the group catalog.
 *
 * `selected` is always fetched, even past the cap — the page it feeds has to render *something*
 * for the row the user is looking at.
 */
export function useSubjectOutputs(subjects: string[], selected: string | undefined): OutputsState {
  const eager = subjects.length <= EAGER_SUBJECT_LIMIT;
  const wanted = useMemo(
    () => (eager ? subjects : subjects.filter((s) => s === selected)),
    [eager, subjects, selected],
  );

  const simulations = useQueries({
    queries: wanted.map((id) => ({ queryKey: ["results-simulations", id], queryFn: () => getSimulationsFor(id) })),
  });
  const flex = useQueries({
    queries: wanted.map((id) => ({ queryKey: ["results-flex-runs", id], queryFn: () => getFlexRuns(id) })),
  });
  const ex = useQueries({
    queries: wanted.map((id) => ({ queryKey: ["results-ex-runs", id, "ex"], queryFn: () => getExRuns(id, "ex") })),
  });
  const mex = useQueries({
    queries: wanted.map((id) => ({ queryKey: ["results-ex-runs", id, "mex"], queryFn: () => getExRuns(id, "mex") })),
  });
  const reports = useQueries({
    queries: wanted.map((id) => ({ queryKey: ["results-reports", id], queryFn: () => getReports(id) })),
  });

  const perSubject: Record<string, SubjectQueries> = {};
  wanted.forEach((id, i) => {
    perSubject[id] = {
      simulations: simulations[i]?.data,
      flexRuns: flex[i]?.data,
      exRuns: ex[i]?.data,
      mexRuns: mex[i]?.data,
      reports: reports[i]?.data,
    };
  });

  // Analyses hang off a simulation, so they can only be asked for once the simulation list is in.
  const analysisPairs = wanted.flatMap((id) => (perSubject[id]?.simulations ?? []).map((s) => ({ subject: id, simulation: s.name })));
  const analyses = useQueries({
    queries: analysisPairs.map((p) => ({
      queryKey: ["results-analyses", p.subject, p.simulation],
      queryFn: () => getAnalyses(p.subject, p.simulation),
    })),
  });
  const analysesBySubject: Record<string, Record<string, Analysis[]>> = {};
  analysisPairs.forEach((p, i) => {
    const rows = analyses[i]?.data;
    if (!rows || rows.length === 0) return;
    (analysesBySubject[p.subject] ??= {})[p.simulation] = rows;
  });

  const group = useQuery({ queryKey: ["results-group"], queryFn: () => getGroupCatalog() });

  const bySubject: Record<string, SubjectOutputs | undefined> = {};
  for (const id of subjects) {
    const q = perSubject[id];
    // A subject is only reported once every one of its five list reads has landed: a partial tree
    // would print a count that shrinks as the rest arrives.
    const ready = q && q.simulations && q.flexRuns && q.exRuns && q.mexRuns && q.reports;
    bySubject[id] = ready
      ? outputsTreeFor(id, {
          simulations: q.simulations!,
          flexRuns: q.flexRuns!,
          exRuns: q.exRuns!,
          mexRuns: q.mexRuns!,
          analyses: analysesBySubject[id] ?? {},
          reports: q.reports!,
        })
      : undefined;
  }

  const pending =
    [...simulations, ...flex, ...ex, ...mex, ...reports, ...analyses].some((q) => q.isPending) || group.isPending;

  return { bySubject, group: group.data ? groupOutputsFor(group.data) : undefined, pending };
}

/** The subject list the Results page shows: every subject, then `Group` pinned last. */
export function subjectRows(subjects: string[]): string[] {
  return [...subjects, GROUP_SUBJECT];
}
