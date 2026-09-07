import { useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Layers, Play } from "lucide-react";
import type { PageDef } from "../../../app/registry";
import { usePageSession } from "../../../app/pageSession";
import { getSubjects } from "../../../api/client";
import { Card, CardBody, CardHeader, PageLayout } from "../../../ui/Layout";
import { ParticipantsField, blockedParticipants, participantsBlockedReason } from "../_participants";
import { usePageScrollMemory } from "../../_shared/session/usePageScrollMemory";
import { Field, TextInput } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { Button } from "../../../ui/Button";
import { HelpIcon } from "../../../ui/HelpPopover";
import { AlertDialog } from "../../../ui/Overlay";
import { notify } from "../../../ui/Toast";
import { ActionBar } from "../../../ui/Chrome";
import { isPanelEnabled, panelDigest } from "../_shared";
import "../panels.css";
import { PlanSummary } from "../PlanSummary";
import { createNiftiAverageJob, getSimulationsFor, planNiftiAverage, validateNiftiAverage } from "./api";
import { buildNiftiAverageConfig, type NiftiAverageRow } from "./config";

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

const SPACE_OPTIONS = [
  { value: "mni", label: "MNI volume" },
  { value: "subject", label: "Subject volume" },
];

/** `tit.stats.nifti_average` needs two participants to average anything (the page's own rule,
 *  unchanged) — stated once so the table and the blocked sentence cannot disagree. */
const MIN_PARTICIPANTS = 2;


/** Why one row cannot take part — the noun phrases `SubjectsField` uses, in row order. */
function rowEligibility(row: Row): { ok: boolean; reason?: string } {
  if (!row.subjectId) return { ok: false, reason: "no subject chosen" };
  if (!row.simulationName) return { ok: false, reason: "no simulation chosen" };
  if (!row.group.trim()) return { ok: false, reason: "no group name" };
  return { ok: true };
}

interface Row extends NiftiAverageRow {
  id: string;
}

let rowSeq = 0;
function newRow(subjectId = "", group = "Group1"): Row {
  rowSeq += 1;
  return { id: `row-${rowSeq}`, subjectId, simulationName: "", group };
}

function NiftiGroupAveragePanel() {
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  usePageScrollMemory();
  const [rows, setRows] = usePageSession<Row[]>("rows", () => [newRow(), newRow()]);
  const [outputName, setOutputName] = usePageSession("outputName", "");
  const [space, setSpace] = usePageSession<"subject" | "mni">("space", "mni");
  const [pattern, setPattern] = usePageSession("pattern", "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz");
  const [diffPairs, setDiffPairs] = usePageSession("diffPairs", "");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const simQueries = useQueries({ queries: rows.map((r) => ({ queryKey: ["simulations", r.subjectId], queryFn: () => getSimulationsFor(r.subjectId), enabled: !!r.subjectId })) });

  const subjectOptions = (subjectsQuery.data ?? []).map((s) => ({ value: s.id, label: s.id }));

  function updateRow(id: string, patch: Partial<Row>) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }
  function addRow() {
    const groups = [...new Set(rows.map((r) => r.group).filter(Boolean))];
    setRows((prev) => [...prev, newRow("", groups[0] ?? "Group1")]);
  }
  function removeRow(id: string) {
    setRows((prev) => prev.filter((r) => r.id !== id));
  }

  const groupsSummary = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of rows) {
      if (!r.subjectId || !r.simulationName || !r.group) continue;
      counts.set(r.group, (counts.get(r.group) ?? 0) + 1);
    }
    return counts;
  }, [rows]);

  const validRows = rows.filter((r) => r.subjectId && r.simulationName && r.group);
  // One sentence for the participants table, from the shared model, and it names the row it means
  // — the same mechanism `SubjectsField` gives the run pages (J3/D5).
  const participantsBlocked = participantsBlockedReason(
    validRows.length,
    blockedParticipants(rows, rowEligibility),
    MIN_PARTICIPANTS,
  );
  const clientErrors: string[] = [];
  if (participantsBlocked) clientErrors.push(participantsBlocked);
  if (!outputName.trim()) clientErrors.push("Enter an analysis name.");

  const diffPairsList = diffPairs
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const config = clientErrors.length === 0 ? buildNiftiAverageConfig({ outputName: outputName.trim(), rows: validRows, space, niftiFilePattern: pattern, diffPairs: diffPairsList }) : null;
  const subjectIds = [...new Set(validRows.map((r) => r.subjectId))];

  const debouncedKey = useDebounced(config ? JSON.stringify({ config, subjectIds }) : "", 350);
  const validateQuery = useQuery({
    queryKey: ["validate-nifti-average", debouncedKey],
    queryFn: () => validateNiftiAverage(JSON.parse(debouncedKey).config),
    enabled: debouncedKey !== "",
  });
  const planQuery = useQuery({
    queryKey: ["plan-nifti-average", debouncedKey],
    queryFn: () => {
      const parsed = JSON.parse(debouncedKey) as { config: ReturnType<typeof buildNiftiAverageConfig>; subjectIds: string[] };
      return planNiftiAverage(parsed.config, parsed.subjectIds);
    },
    enabled: debouncedKey !== "" && validateQuery.data?.ok === true,
  });

  const serverErrors = validateQuery.data?.errors.map((e) => `${e.path ? `${e.path}: ` : ""}${e.message}`) ?? [];

  function handleRunClick() {
    if (!config) {
      notify.error(clientErrors[0] ?? "Complete the analysis configuration before running.");
      return;
    }
    setConfirmOpen(true);
  }

  async function run() {
    if (!config) return;
    setSubmitting(true);
    try {
      await createNiftiAverageJob(config, subjectIds);
      notify.success(`Queued: NIfTI group average "${config.output_name}"`);
      setConfirmOpen(false);
    } catch {
      notify.error("Could not queue the group-averaging job.");
    } finally {
      setSubmitting(false);
    }
  }

  const digest = panelDigest(clientErrors, planQuery.data, config !== null && (validateQuery.isPending || planQuery.isFetching));

  return (
    <PageLayout
      actionBar={
        <ActionBar
          digest={digest}
          blocked={clientErrors.length > 0}
          primary={
            <Button
              variant="primary"
              icon={<Play size={14} />}
              loading={submitting}
              disabled={clientErrors.length > 0}
              onClick={handleRunClick}
              data-testid="run-button"
              title={clientErrors[0] ?? undefined}
            >
              Run analysis
            </Button>
          }
        />
      }
    >
      <div className="panel-page">
        <div className="panel-page-split">
          <div className="panel-page-col">
            <ParticipantsField
              rows={rows}
              rowId={(r) => r.id}
              subjectOf={(r) => r.subjectId}
              eligibility={rowEligibility}
              note="one job over all subjects"
              onAdd={addRow}
              onRemove={removeRow}
              fill
              loading={subjectsQuery.isPending}
              help={
                <HelpIcon title="NIfTI group average" label="About this page" text="Compute group averages and differences of NIfTI files." />
              }
              subjectCell={(row) => (
                <Select
                  value={row.subjectId || undefined}
                  onValueChange={(v) => updateRow(row.id, { subjectId: v, simulationName: "" })}
                  options={subjectOptions}
                  placeholder="Subject"
                />
              )}
              simulationCell={(row, i) => (
                <Select
                  value={row.simulationName || undefined}
                  onValueChange={(v) => updateRow(row.id, { simulationName: v })}
                  options={(simQueries[i]?.data ?? []).map((s) => ({ value: s.name, label: s.name }))}
                  placeholder={row.subjectId ? "Simulation" : "Pick a subject first"}
                  disabled={!row.subjectId}
                />
              )}
              columns={[
                {
                  id: "group",
                  header: "Group",
                  cell: (row) => (
                    <TextInput
                      value={row.group}
                      placeholder="Group"
                      aria-label={`Group for row ${rows.indexOf(row) + 1}`}
                      onChange={(e) => updateRow(row.id, { group: e.target.value })}
                    />
                  ),
                },
              ]}
            />
          </div>
          <div className="panel-page-col">

          <Card>
            <CardHeader title="Analysis configuration" />
            <CardBody>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                <Field label="Analysis name" htmlFor="nga-output-name" required>
                  <TextInput id="nga-output-name" value={outputName} placeholder="e.g. hippocampus_group_comparison" onChange={(e) => setOutputName(e.target.value)} />
                </Field>
                <Field label="Space" htmlFor="nga-space">
                  <Select id="nga-space" value={space} onValueChange={(v) => setSpace(v as "subject" | "mni")} options={SPACE_OPTIONS} />
                </Field>
                <Field label="NIfTI pattern" htmlFor="nga-pattern" help="Use {simulation_name} as a variable — the subject is already in the directory path.">
                  <TextInput id="nga-pattern" value={pattern} onChange={(e) => setPattern(e.target.value)} />
                </Field>
                <Field label="Group differences" htmlFor="nga-diff-pairs" help="Comma-separated GroupA-GroupB pairs. Leave empty to compute all possible differences.">
                  <TextInput id="nga-diff-pairs" value={diffPairs} placeholder="e.g. Group1-Group2, Group1-Group3" onChange={(e) => setDiffPairs(e.target.value)} />
                </Field>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Plan" />
            <CardBody>
              <PlanSummary
                plan={planQuery.data}
                loading={config !== null && (validateQuery.isPending || planQuery.isFetching)}
                error={planQuery.error ? "Could not compute the plan." : undefined}
                serverErrors={serverErrors}
                idleMessage="Complete the analysis configuration above to see its plan."
              />
            </CardBody>
          </Card>
          </div>
        </div>
      </div>

      <AlertDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Run group averaging?"
        description={`Groups: ${[...groupsSummary.entries()].map(([g, n]) => `${g} (${n} subjects)`).join(", ")}. Analysis name: ${outputName.trim()}.`}
        confirmLabel="Run analysis"
        confirmVariant="primary"
        onConfirm={() => void run()}
      />
    </PageLayout>
  );
}

const page: PageDef = {
  id: "panel-nifti-group-average",
  title: "NIfTI group averaging",
  purpose: "Compute group averages and differences of NIfTI files.",
  navGroup: "panels",
  order: 110,
  icon: Layers,
  Component: NiftiGroupAveragePanel,
  enabled: isPanelEnabled("nifti-group-average"),
};

export default page;
