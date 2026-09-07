/**
 * Subject Info Viewer — the v3 home of `tit/gui/extensions/subject_info_viewer.py` (454 lines).
 *
 * The Qt dialog was a project-wide presence grid with a JSON export. That grid is now the Overview
 * page's job (DESIGN.md §9), and duplicating it here would be a second answer to "what does this
 * project have" that can disagree with the first. What the extension *also* had, and nothing in v3
 * replaced, is `get_detailed_subject_info()` — the per-subject inventory: which anatomical files
 * exist, which `m2m_*` directories, which simulations and what each one has been analysed with,
 * which optimisation runs, which saved free-hand sets and reports. That is this page.
 *
 * Three rules, each with the failure it prevents:
 *
 *  - **One subject at a time, chosen in `SubjectsField`'s `single` mode.** The grammar every other
 *    page picks subjects with (plan §3, J1–J4), not a bespoke dropdown — and `single` says in the
 *    summary line that this page reads one subject, so a user cannot tick three and wonder which
 *    one the cards describe.
 *  - **One request, not a dozen.** `GET /api/subjects/{id}/info` assembles the whole picture
 *    server-side. Composing it from the per-kind `/api/catalog/*` routes in the browser would give
 *    the user a page whose partial failures they have to interpret.
 *  - **Nothing here is a path.** The Qt dialog printed absolute container paths into a table; the
 *    only path v3 shows is the head model's, in the summary, because that is the one a user types
 *    into a shell. Everything else is a name and a size.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ClipboardList, Download, RefreshCw } from "lucide-react";
import type { PageDef } from "../../../app/registry";
import { usePageSession } from "../../../app/pageSession";
import { getSubjects } from "../../../api/client";
import { Card, CardBody, CardHeader, PageLayout } from "../../../ui/Layout";
import { DataTable, type DataTableColumn } from "../../../ui/DataTable";
import { Button } from "../../../ui/Button";
import { Chip } from "../../../ui/Status";
import { Callout, DefinitionList, EmptyState, Skeleton } from "../../../ui/Feedback";
import { notify } from "../../../ui/Toast";
import { SubjectsField, presenceColumns } from "../../_shared/subjects";
import { usePageScrollMemory } from "../../_shared/session/usePageScrollMemory";
import { isPanelEnabled } from "../_shared";
import "../panels.css";
import "./subject-info.css";
import { getSubjectInfo, type FileRef, type SubjectInfo, type SubjectSimulationInfo } from "./api";

/** Every readiness column the catalog carries, because this page's whole job is completeness. */
const INFO_COLUMNS = presenceColumns<{
  id: string;
  has_raw: boolean;
  has_fastsurfer: boolean;
  has_freesurfer: boolean;
  has_m2m: boolean;
  has_dwi?: boolean;
  has_ct?: boolean;
}>({ dwi: true, ct: true });

/** Bytes as the shortest honest unit. `size_bytes` is an integer from `os.stat`, so no rounding
 *  question arises below 1 kB — it is printed exactly. */
function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["kB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

const FILE_COLUMNS: DataTableColumn<FileRef>[] = [
  {
    id: "name",
    header: "File",
    accessorKey: "name",
    cell: ({ getValue }) => <span className="mono">{String(getValue())}</span>,
  },
  {
    id: "size",
    header: "Size",
    accessorKey: "size_bytes",
    numeric: true,
    cell: ({ getValue }) => <span className="tabular-nums">{humanSize(Number(getValue()))}</span>,
  },
];

const SIMULATION_COLUMNS: DataTableColumn<SubjectSimulationInfo>[] = [
  {
    id: "name",
    header: "Simulation",
    accessorKey: "name",
    cell: ({ getValue }) => <span className="mono">{String(getValue())}</span>,
  },
  {
    id: "modes",
    header: "Modes",
    enableSorting: false,
    cell: ({ row }) => (
      <span className="subject-info-chips">
        <Chip kind={row.original.has_ti ? "success" : "neutral"} missing={!row.original.has_ti}>
          TI
        </Chip>
        <Chip kind={row.original.has_mti ? "success" : "neutral"} missing={!row.original.has_mti}>
          mTI
        </Chip>
      </span>
    ),
  },
  { id: "meshes", header: "Meshes", accessorKey: "n_meshes", numeric: true },
  {
    id: "analyses",
    header: "Analyses",
    numeric: true,
    accessorFn: (row) => row.analyses.length,
    // The names, not just the count: "3" does not tell a user whether the ROI they care about has
    // been measured, and the count alone is what the Qt table showed.
    cell: ({ row }) =>
      row.original.analyses.length === 0 ? (
        <span className="subject-info-none">none</span>
      ) : (
        <span title={row.original.analyses.join("\n")}>{row.original.analyses.length}</span>
      ),
  },
];

/**
 * A list of names, or the one word that says there are none — never an empty cell.
 *
 * Capped, because these lists are unbounded on real data: `sub-ernie` in Dataset 000 has 42
 * reports, and 42 chips is a wall that buries the six rows around it. The overflow chip carries
 * the whole list in its tooltip, so nothing is unreachable — only unprinted.
 */
const NAME_LIST_MAX = 8;

function NameList({ names }: { names: string[] }) {
  if (names.length === 0) return <span className="subject-info-none">none</span>;
  const shown = names.slice(0, NAME_LIST_MAX);
  const rest = names.length - shown.length;
  return (
    <span className="subject-info-chips">
      {shown.map((name) => (
        <Chip key={name} kind="neutral">
          {name}
        </Chip>
      ))}
      {rest > 0 && (
        <Chip kind="neutral" title={names.join("\n")}>
          +{rest} more
        </Chip>
      )}
    </span>
  );
}

function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function FilesCard({ title, files, empty }: { title: string; files: FileRef[]; empty: string }) {
  return (
    <Card className="panel-fill-card">
      <CardHeader title={`${title}${files.length > 0 ? ` · ${files.length}` : ""}`} />
      <CardBody>
        {/* DESIGN.md §4.4: when the populated state is a table, the empty state is that same table
            with its headers and the message in the body — not a centred sentence. */}
        <DataTable data={files} columns={FILE_COLUMNS} getRowId={(f) => f.name} emptyMessage={empty} minRows={3} />
      </CardBody>
    </Card>
  );
}

function SubjectDetail({ info }: { info: SubjectInfo }) {
  const anat = info.anat_files as FileRef[];
  const dwi = info.dwi_files as FileRef[];
  const source = info.sourcedata_files as FileRef[];

  return (
    <>
      <Card>
        <CardHeader
          title="Summary"
          actions={
            <Button
              variant="secondary"
              size="sm"
              icon={<Download size={14} />}
              onClick={() => {
                downloadJson(`subject-info-${info.id}.json`, info);
                notify.success(`Exported ${info.id}'s information.`);
              }}
            >
              Export JSON
            </Button>
          }
        />
        <CardBody>
          <DefinitionList
            entries={[
              ["Subject", <span className="mono">{info.id}</span>],
              [
                "Stages",
                <span className="subject-info-chips">
                  {(
                    [
                      ["raw", info.has_raw],
                      ["fastsurfer", info.has_fastsurfer],
                      ["freesurfer", info.has_freesurfer],
                      ["m2m", info.has_m2m],
                      ["dwi", info.has_dwi],
                      ["ct", info.has_ct],
                    ] as [string, boolean][]
                  ).map(([label, on]) => (
                    <Chip key={label} kind={on ? "success" : "neutral"} missing={!on}>
                      {label}
                    </Chip>
                  ))}
                </span>,
              ],
              ["Anatomy", <NameList names={info.anat_modalities} />],
              ["Head model", info.m2m_path ? <span className="mono">{info.m2m_path}</span> : <span className="subject-info-none">not built</span>],
              ["m2m directories", <NameList names={info.m2m_dirs} />],
              ["EEG nets", <NameList names={info.eeg_nets} />],
              ["Leadfields", <NameList names={info.has_leadfields} />],
              [
                "Runs",
                <span className="subject-info-counts">
                  {info.simulations.length} simulation{info.simulations.length === 1 ? "" : "s"} · {info.n_analyses} analys
                  {info.n_analyses === 1 ? "is" : "es"} · {info.flex_search.length} flex · {info.ex_search.length} ex ·{" "}
                  {info.mex_search.length} mEx
                </span>,
              ],
            ]}
          />
        </CardBody>
      </Card>

      <Card className="panel-fill-card">
        <CardHeader title={`Simulations · ${info.simulations.length}`} />
        <CardBody>
          <DataTable
            data={info.simulations as SubjectSimulationInfo[]}
            columns={SIMULATION_COLUMNS}
            getRowId={(s) => s.name}
            emptyMessage="No simulations have been run for this subject."
            minRows={3}
          />
        </CardBody>
      </Card>

      <div className="panel-page-columns">
        <FilesCard title="Anatomical files" files={anat} empty="No BIDS anat/ files." />
        <FilesCard title="DWI files" files={dwi} empty="No BIDS dwi/ files." />
        <FilesCard title="Source data" files={source} empty="Nothing staged under sourcedata/." />
      </div>

      <Card>
        <CardHeader title="Derivatives" />
        <CardBody>
          <DefinitionList
            entries={[
              ["Flex-search", <NameList names={info.flex_search} />],
              ["Ex-search", <NameList names={info.ex_search} />],
              ["mEx-search", <NameList names={info.mex_search} />],
              ["Free-hand sets", <NameList names={info.freehand_configs} />],
              ["Reports", <NameList names={info.reports} />],
            ]}
          />
        </CardBody>
      </Card>
    </>
  );
}

function SubjectInfoPanel() {
  const navigate = useNavigate();
  usePageScrollMemory();
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  const subjects = useMemo(() => subjectsQuery.data ?? [], [subjectsQuery.data]);
  const [selected, setSelected] = usePageSession<string[]>("subjects", []);

  // `single` mode keeps the array to one id; reading `[0]` is therefore the whole selection, not
  // "the first of several the page silently ignores".
  const subjectId = selected[0] ?? null;
  const infoQuery = useQuery({
    queryKey: ["subject-info", subjectId],
    queryFn: () => getSubjectInfo(subjectId as string),
    enabled: !!subjectId,
  });

  return (
    <PageLayout variant="browse" className="panel-page">
      <div className="panel-page-split">
        <div className="panel-page-col">
          <SubjectsField
            subjects={subjects}
            value={selected}
            onChange={setSelected}
            columns={INFO_COLUMNS}
            mode="single"
            defaultOpen
            fill
            loading={subjectsQuery.isPending}
            emptyMessage="This project has no subjects yet."
          />
        </div>
        <div className="panel-page-col subject-info-detail" data-testid="subject-info-detail">
          {!subjectId && (
            <Card>
              <CardBody>
                <EmptyState
                  icon={<ClipboardList size={24} />}
                  message={
                    subjects.length === 0
                      ? "No subjects in this project yet."
                      : "Choose a subject to see everything it has on disk."
                  }
                  actionLabel={subjects.length === 0 ? "Run pre-processing" : undefined}
                  onAction={subjects.length === 0 ? () => navigate("/preprocess") : undefined}
                />
              </CardBody>
            </Card>
          )}
          {subjectId && infoQuery.isPending && <Skeleton height={320} />}
          {subjectId && infoQuery.error && (
            <Callout kind="danger" title={`Could not read ${subjectId}`}>
              {infoQuery.error instanceof Error ? infoQuery.error.message : "The server did not answer."}{" "}
              <Button variant="ghost" size="sm" icon={<RefreshCw size={14} />} onClick={() => void infoQuery.refetch()}>
                Retry
              </Button>
            </Callout>
          )}
          {infoQuery.data && <SubjectDetail info={infoQuery.data} />}
        </div>
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "panel-subject-info",
  title: "Subject info",
  purpose: "Everything one subject has on disk: anatomy, head model, runs and derivatives.",
  navGroup: "panels",
  order: 140,
  icon: ClipboardList,
  Component: SubjectInfoPanel,
  enabled: isPanelEnabled("subject-info"),
};

export default page;
