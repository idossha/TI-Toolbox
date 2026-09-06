/**
 * The cohort node's editor: which subjects this graph is about.
 *
 * It is the Overview's own presence columns beside the same `SelectionList` every other page picks
 * subjects with (DESIGN §4.4.1), reading `GET /api/catalog/overview` through the Overview page's
 * own client — not a second copy of either. Which matters here more than usual, because the *same*
 * facts decide what this cohort may be wired to: a row that reads "no head model" is a row that
 * will make a wire to the Simulator refuse, and seeing both in one place is the difference between
 * a refusal that is obvious and one that is mysterious.
 *
 * Each row states what it is ready for, so the reason arrives before the refusal does.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { SelectionList, type SelectionItem } from "../../ui/SelectionList";
import { StatusDot, type SemanticKind } from "../../ui/Status";
import { InlineError } from "../../ui/Feedback";
import { getOverview, type OverviewSubject, type PresenceState } from "../overview/api";
import { CAPABILITY_LABEL, READINESS, type Capability, type NodeKind, type Readiness } from "./graph";

/** The presence columns this page cares about, in workflow order. */
const COLUMNS: { key: "raw" | "m2m" | "leadfield"; head: string }[] = [
  { key: "raw", head: "Raw" },
  { key: "m2m", head: "Head model" },
  { key: "leadfield", head: "Leadfield" },
];

const DOT: Record<string, SemanticKind> = {
  present: "success",
  partial: "warning",
  absent: "neutral",
  failed: "danger",
  pending: "accent",
  running: "accent",
  queued: "accent",
};

/** Mirrors `tit.pipeline.validate.readiness_from_overview` — the client's copy of the same read. */
export function readinessFromOverview(subjects: OverviewSubject[]): Readiness {
  const out: Readiness = {};
  for (const row of subjects) {
    const caps: Capability[] = [];
    if (row.raw === "present") caps.push("raw");
    if (row.m2m === "present") caps.push("m2m");
    // A leadfield is per EEG net, not per subject, so `partial` genuinely is "has a leadfield".
    if (row.leadfield === "present" || row.leadfield === "partial") caps.push("leadfield");
    if ((row.counts?.simulations ?? 0) > 0) caps.push("simulation");
    out[row.id] = caps;
  }
  return out;
}

/** The kinds a cohort with these capabilities may be wired straight into, in palette order. */
function acceptedBy(caps: Capability[]): NodeKind[] {
  const have = new Set(caps);
  return (Object.keys(READINESS) as NodeKind[]).filter(
    (kind) => kind !== "subjects" && READINESS[kind].requires.every((c) => have.has(c)),
  );
}

export function useOverviewReadiness() {
  const query = useQuery({ queryKey: ["overview"], queryFn: () => getOverview(), staleTime: 30_000 });
  const readiness = useMemo(() => readinessFromOverview(query.data?.subjects ?? []), [query.data]);
  return { ...query, readiness };
}

export function SubjectsEditor({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["overview"],
    queryFn: () => getOverview(),
    staleTime: 30_000,
  });
  const rows = useMemo(() => data?.subjects ?? [], [data]);
  const readiness = useMemo(() => readinessFromOverview(rows), [rows]);

  const items: SelectionItem[] = useMemo(
    () =>
      rows.map((row) => {
        const caps = readiness[row.id] ?? [];
        const accepts = acceptedBy(caps);
        return {
          id: row.id,
          label: row.id,
          search: `${row.id} ${caps.join(" ")}`,
          value: row,
          // Not a "why not": every subject may be *chosen*. What varies is what the cohort can
          // then be wired to, which is what this says.
          reason: accepts.length
            ? `ready for ${accepts.join(", ")}`
            : `no ${CAPABILITY_LABEL.raw} yet — nothing can run on this subject`,
          data: { caps: caps.join(",") },
        } satisfies SelectionItem;
      }),
    [rows, readiness],
  );

  if (isError) {
    return (
      <InlineError
        message="Could not read the project's subjects."
        detail={String((error as Error)?.message ?? error)}
        onAction={() => void refetch()}
      />
    );
  }

  return (
    <SelectionList
      label="Subjects"
      aria="grid"
      items={items}
      value={value}
      onChange={onChange}
      loading={isPending}
      testId="pipeline-subjects"
      filterTestId="pipeline-subjects-filter"
      emptyMessage="This project has no subjects yet."
      maxHeight={320}
      headers={{ label: "Subject", reason: "Ready for" }}
      columns={COLUMNS.map((column) => ({
        id: column.key,
        header: column.head,
        cell: (item: SelectionItem) => {
          const row = item.value as OverviewSubject;
          const state = (row?.[column.key] ?? "absent") as PresenceState;
          return <StatusDot kind={DOT[state] ?? "neutral"} title={state} />;
        },
      }))}
    />
  );
}
