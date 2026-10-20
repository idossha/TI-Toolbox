/**
 * EEG caps — map MNI electrode caps onto a head model that already exists, without re-running
 * charm, and inspect a net on the subject's scalp (`docs/dev/ARCHITECTURE.md` § 8, EEG caps).
 *
 * No job: a warp is seconds (`tit/server/routes/caps.py`), so Apply is a request and its answer
 * refreshes the list. Replacing a net already on the subject goes through the one existing-outputs
 * dialog, and the server's 409 opens that dialog too when the list was stale.
 */
import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleDot, Upload } from "lucide-react";
import type { PageDef } from "../../../app/registry";
import { usePageSession } from "../../../app/pageSession";
import { getSubjects } from "../../../api/client";
import { useSubjectContext } from "../../../app/subjectContext";
import { Card, CardBody, CardHeader, PageLayout } from "../../../ui/Layout";
import { SubjectsField, presenceColumns } from "../../_shared/subjects";
import { usePageScrollMemory } from "../../_shared/session/usePageScrollMemory";
import { ScenePane } from "../../_shared/scene";
import type { SceneMarker } from "../../_shared/scene/model";
import { ExistingOutputsDialog, isExistingOutputsConflict } from "../../_shared/run/ExistingOutputsDialog";
import { DataTable, type DataTableColumn } from "../../../ui/DataTable";
import { Field } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { Checkbox } from "../../../ui/Toggle";
import { Button } from "../../../ui/Button";
import { Chip } from "../../../ui/Status";
import { HelpIcon } from "../../../ui/HelpPopover";
import { DOCS_SITE } from "../../help/api";
import { ReadMore } from "../../preprocess/stepInfo";
import { ActionBar } from "../../../ui/Chrome";
import { notify, notifySubmitError } from "../../../ui/Toast";
import { isPanelEnabled } from "../_shared";
import "../panels.css";
import { getAvailableCaps, inspectNet, uploadCap, warpCaps, type CapStatus } from "./api";
import { CAPS_HELP, INSPECT_HELP, NO_HEAD_MODEL, appliedDate, capLabel, capStatus, defaultCapsSubject, electrodeColumns, existingAmong, inspectionMarkers, inspectionWarnings, mm, reapplicable, sourceLabel } from "./model";

const WIKI = `${DOCS_SITE}wiki/eeg-caps/`;

const SUBJECT_COLUMNS = presenceColumns<{ id: string; has_raw: boolean; has_fastsurfer: boolean; has_freesurfer: boolean; has_m2m: boolean }>();
const NONE = "__none__";
const NO_MARKERS: SceneMarker[] = [];

function CapsPanel() {
  usePageScrollMemory();
  const queryClient = useQueryClient();
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  const [subjects, setSubjects] = usePageSession<string[]>("subjects", []);
  const subject = subjects[0] ?? "";
  // Open on a subject rather than empty: the app's current one when it has a head model, else the
  // first that does — once per visit, adjusted during render (not an effect), like the Simulator's
  // first row; a selection the page already holds is kept.
  const shellSubject = useSubjectContext((s) => s.subjectId);
  const [seeded, setSeeded] = useState(false);
  const fallback = subjectsQuery.data ? defaultCapsSubject(subjectsQuery.data, shellSubject) : null;
  if (!seeded && subjectsQuery.data) {
    setSeeded(true);
    if (subjects.length === 0 && fallback) setSubjects([fallback]);
  }
  const [picked, setPicked] = useState<string[]>([]);
  const [net, setNet] = usePageSession("net", "");
  const [compare, setCompare] = usePageSession("compare", "");
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<{ names: string[]; existing: string[] } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const capsQuery = useQuery({ queryKey: ["caps", subject], queryFn: () => getAvailableCaps(subject), enabled: !!subject });
  const caps = useMemo(() => capsQuery.data ?? [], [capsQuery.data]);
  const onSubject = caps.filter((c) => c.on_subject).map((c) => c.name);
  const viewNet = onSubject.includes(net) ? net : (onSubject[0] ?? "");
  const compareNet = compare && compare !== viewNet && onSubject.includes(compare) ? compare : "";

  const inspectQuery = useQuery({
    queryKey: ["caps-inspect", subject, viewNet, compareNet],
    queryFn: () => inspectNet(subject, viewNet, compareNet),
    enabled: !!subject && !!viewNet,
    retry: false,
    // Switching nets keeps the previous net's table on screen until the new one lands, instead of
    // collapsing the page to nothing for the round trip.
    placeholderData: (previous, query) => (query?.queryKey[1] === subject ? previous : undefined),
  });
  const inspection = inspectQuery.data;
  const markers = useMemo(() => (inspection ? inspectionMarkers(inspection) : undefined), [inspection]);
  const warnings = inspection ? inspectionWarnings(inspection) : [];

  async function apply(names: string[], overwrite: boolean) {
    if (names.length === 0) return;
    setBusy(true);
    try {
      const written = await warpCaps(subject, names, overwrite);
      notify.success(`Applied ${written.length === 1 ? capLabel(written[0]!) : `${written.length} caps`} to ${subject}`);
      setPicked([]);
      setConfirm(null);
      await queryClient.invalidateQueries({ queryKey: ["caps", subject] });
      await queryClient.invalidateQueries({ queryKey: ["caps-inspect", subject] });
      await queryClient.invalidateQueries({ queryKey: ["scene", "electrodes", subject] });
    } catch (error) {
      if (isExistingOutputsConflict(error)) setConfirm({ names, existing: existingAmong(caps, names).length ? existingAmong(caps, names) : names });
      else notifySubmitError("Could not apply the cap.", error);
    } finally {
      setBusy(false);
    }
  }

  function requestApply(names: string[]) {
    const existing = existingAmong(caps, names);
    if (existing.length > 0) setConfirm({ names, existing });
    else void apply(names, false);
  }

  async function onUpload(file: File | undefined) {
    if (!file) return;
    try {
      const added = await uploadCap(file);
      notify.success(`Added ${capLabel(added.name)} (${added.electrodes} electrodes) to this project's caps`);
      await queryClient.invalidateQueries({ queryKey: ["caps"] });
    } catch (error) {
      notifySubmitError("Could not add the cap.", error);
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  const capColumns: DataTableColumn<CapStatus>[] = [
    {
      id: "pick",
      header: "",
      enableSorting: false,
      cell: ({ row }) =>
        row.original.source === null ? null : (
          <span onClick={(e) => e.stopPropagation()}>
            <Checkbox
              aria-label={`Select ${capLabel(row.original.name)}`}
              checked={picked.includes(row.original.name)}
              onCheckedChange={(on) => setPicked((prev) => (on ? [...prev, row.original.name] : prev.filter((n) => n !== row.original.name)))}
            />
          </span>
        ),
    },
    { id: "name", accessorFn: (c) => capLabel(c.name), header: "Cap" },
    { id: "source", accessorFn: sourceLabel, header: "Source" },
    {
      id: "status",
      accessorFn: (c) => capStatus(c).label,
      header: "Status",
      cell: ({ row }) => {
        const s = capStatus(row.original);
        return <Chip kind={s.kind} dot title={s.title}>{s.label}</Chip>;
      },
    },
    { id: "applied", accessorFn: (c) => c.subject_mtime ?? 0, header: "Applied", cell: ({ row }) => appliedDate(row.original) },
  ];

  const columns = useMemo(() => electrodeColumns(inspection?.compare?.net ?? null), [inspection]);
  const electrodeRows = useMemo(() => (inspection?.electrodes ?? []).map((e, index) => ({ ...e, index })), [inspection]);
  const summary = inspection?.summary;

  const noHeadModel = !!subjectsQuery.data && fallback === null;
  const digest = !subject
    ? noHeadModel ? NO_HEAD_MODEL : "Select a subject with a head model."
    : picked.length === 0
      ? `${onSubject.length} of ${caps.length} caps on ${subject}`
      : `${picked.length} cap${picked.length === 1 ? "" : "s"} selected`;
  const allNames = reapplicable(caps);

  return (
    <PageLayout
      variant="run"
      rightPane={
        <div className="caps-scene" data-testid="caps-scene">
          {/* Mounted as soon as there is a subject, so the head loads while the caps list and the
              inspection are still on their way; the electrodes arrive as a marker layer. */}
          {subject ? (
            <ScenePane
              mode="montage"
              subject={subject}
              placedMarkers={markers ?? NO_MARKERS}
              selectedMarkers={selectedRow === null ? undefined : [selectedRow]}
              onPlacedPick={(index) => setSelectedRow(index)}
              note={
                !viewNet
                  ? capsQuery.isPending ? `Loading caps on ${subject}…` : "No net on this subject yet — apply a cap."
                  : inspection?.compare ? `${viewNet} (blue) and ${inspection.compare.net} (orange) on ${subject}` : `${viewNet} on ${subject}`
              }
            />
          ) : (
            <p className="field-help">{noHeadModel ? NO_HEAD_MODEL : "Pick a subject to see its nets on the scalp."}</p>
          )}
        </div>
      }
      actionBar={
        <ActionBar
          digest={digest}
          blocked={!subject}
          secondary={
            <Button variant="secondary" disabled={!subject || allNames.length === 0} loading={busy} onClick={() => requestApply(allNames)} data-testid="caps-reapply-all">
              Re-apply all
            </Button>
          }
          primary={
            <Button variant="primary" disabled={!subject || picked.length === 0} loading={busy} onClick={() => requestApply(picked)} data-testid="caps-apply">
              Apply selected
            </Button>
          }
        />
      }
    >
      <div className="panel-page">
        <div data-tier="1">
          <SubjectsField
            subjects={subjectsQuery.data ?? []}
            value={subjects}
            onChange={(ids) => {
              setSubjects(ids.slice(0, 1));
              setPicked([]);
              setSelectedRow(null);
            }}
            columns={SUBJECT_COLUMNS}
            eligibility={(s) => (s.has_m2m ? { ok: true } : { ok: false, reason: "no head model (m2m)" })}
            mode="single"
            defaultOpen
            loading={subjectsQuery.isPending}
          />
        </div>
        <div className="panel-page-columns">
          <Card>
            <CardHeader
              title="Caps"
              actions={
                <div className="caps-header-actions">
                  <input ref={fileInput} type="file" accept=".csv,text/csv" hidden data-testid="caps-upload-input" onChange={(e) => void onUpload(e.target.files?.[0])} />
                  <Button variant="ghost" size="sm" icon={<Upload size={14} />} onClick={() => fileInput.current?.click()}>
                    Add MNI cap…
                  </Button>
                  <HelpIcon title="EEG caps" label="About caps" text={CAPS_HELP} testId="caps-help">
                    <div className="help-footer"><ReadMore href={`${WIKI}#apply-a-cap`} /></div>
                  </HelpIcon>
                </div>
              }
            />
            <CardBody>
              <div data-testid="caps-table">
                <DataTable
                  data={caps}
                  columns={capColumns}
                  getRowId={(c) => c.name}
                  onRowClick={(c) => c.on_subject && setNet(c.name)}
                  emptyMessage={subject ? (capsQuery.isPending ? "Loading caps…" : "No caps found.") : "Pick a subject."}
                />
              </div>
              <p className="field-help">
                Applying warps the MNI cap onto this head exactly as charm does and writes it to <code>m2m_{subject || "…"}/eeg_positions/</code>. Click a cap on the subject to inspect it.
              </p>
            </CardBody>
          </Card>
          <Card>
            <CardHeader
              title="Inspect"
              actions={
                <HelpIcon title="Inspect a net" label="About inspecting" text={INSPECT_HELP} testId="caps-inspect-help">
                  <div className="help-footer"><ReadMore href={`${WIKI}#inspect-a-net`} /></div>
                </HelpIcon>
              }
            />
            <CardBody>
              <div className="form-grid">
                <Field label="Net" htmlFor="caps-net">
                  <Select id="caps-net" value={viewNet || undefined} onValueChange={(v) => { setNet(v); setSelectedRow(null); }} options={onSubject.map((n) => ({ value: n, label: capLabel(n) }))} placeholder="Net" disabled={onSubject.length === 0} />
                </Field>
                <Field label="Compare with" htmlFor="caps-compare">
                  <Select
                    id="caps-compare"
                    value={compareNet || NONE}
                    onValueChange={(v) => setCompare(v === NONE ? "" : v)}
                    options={[{ value: NONE, label: "None" }, ...onSubject.filter((n) => n !== viewNet).map((n) => ({ value: n, label: capLabel(n) }))]}
                    disabled={onSubject.length < 2}
                  />
                </Field>
              </div>
              {(inspectQuery.isPending || inspectQuery.isPlaceholderData) && viewNet && <p className="field-help" role="status" data-testid="caps-inspecting">Inspecting {capLabel(viewNet)}…</p>}
              {inspectQuery.error && <p className="field-help" role="status">Could not inspect {capLabel(viewNet)}: {inspectQuery.error.message}</p>}
              {summary && (
                <div className="caps-chips" data-testid="caps-summary">
                  <Chip>{summary.count} electrodes</Chip>
                  <Chip>spacing {mm(summary.nn_median_mm)} mm median · {mm(summary.nn_min_mm)} min</Chip>
                  <Chip>scalp ≤ {mm(summary.scalp_max_mm)} mm</Chip>
                  {inspection?.compare && <Chip kind="accent">Δ {capLabel(inspection.compare.net)}: {mm(inspection.compare.median_mm)} mm median</Chip>}
                  {warnings.length > 0 ? (
                    <Chip kind="danger" dot title={warnings.join("\n")}>
                      {warnings.length} warning{warnings.length === 1 ? "" : "s"}
                    </Chip>
                  ) : (
                    <Chip kind="success" dot>no collapsed or duplicate electrodes</Chip>
                  )}
                </div>
              )}
              {warnings.map((w) => (
                <p key={w} className="field-help" data-testid="caps-warning">{w}</p>
              ))}
            </CardBody>
          </Card>
        </div>
        {inspection && (
          <Card>
            <CardHeader title={`Electrodes · ${capLabel(inspection.net)}`} />
            <CardBody>
              <div className="caps-electrodes" data-testid="caps-electrodes">
                <DataTable data={electrodeRows} columns={columns} getRowId={(r) => String(r.index)} selected={selectedRow === null ? {} : { [String(selectedRow)]: true }} onRowClick={(r) => setSelectedRow(r.index)} />
              </div>
            </CardBody>
          </Card>
        )}
      </div>
      <ExistingOutputsDialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        existing={confirm?.existing.length ?? 0}
        total={confirm?.names.length ?? 0}
        noun="EEG cap"
        busy={busy}
        onDecide={(decision) => {
          if (!confirm) return;
          if (decision === "replace") void apply(confirm.names, true);
          else {
            const fresh = confirm.names.filter((n) => !confirm.existing.includes(n));
            setConfirm(null);
            void apply(fresh, false);
          }
        }}
      />
    </PageLayout>
  );
}

const page: PageDef = {
  id: "panel-caps",
  title: "EEG caps",
  purpose: "Map MNI electrode caps onto an existing head model and inspect nets on the scalp.",
  navGroup: "panels",
  order: 140,
  icon: CircleDot,
  Component: CapsPanel,
  enabled: isPanelEnabled("caps"),
};

export default page;
