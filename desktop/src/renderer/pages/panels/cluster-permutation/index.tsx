import { useEffect, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { GitCompare, Play } from "lucide-react";
import type { PageDef } from "../../../app/registry";
import { usePageSession } from "../../../app/pageSession";
import { getSubjects } from "../../../api/client";
import { Card, CardBody, CardHeader, PageLayout } from "../../../ui/Layout";
import { ParticipantsField, blockedParticipants, participantsBlockedReason } from "../_participants";
import { usePageScrollMemory } from "../../_shared/session/usePageScrollMemory";
import { Field, TextInput } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { NumberInput } from "../../../ui/NumberInput";
import { Checkbox } from "../../../ui/Toggle";
import { SegmentedControl } from "../../../ui/SegmentedControl";
import { Button } from "../../../ui/Button";
import { HelpIcon } from "../../../ui/HelpPopover";
import { notify } from "../../../ui/Toast";
import { ActionBar } from "../../../ui/Chrome";
import { isPanelEnabled, panelDigest } from "../_shared";
import "../panels.css";
import { PlanSummary } from "../PlanSummary";
import { ExtensionRunPanel, useExtensionJobs } from "../ExtensionRunPanel";
import { createStatsJob, getSimulationsFor, planStats, validateStats, type CorrelationConfig, type GroupComparisonConfig } from "./api";
import { buildCorrelationConfig, buildGroupComparisonConfig, type SharedStatsFields } from "./config";

type Mode = "classification" | "correlation";

interface SubjectRow {
  id: string;
  subjectId: string;
  simulationName: string;
  response: 0 | 1;
  effectSize: number | undefined;
  weight: number | undefined;
}

let rowSeq = 0;
function newRow(): SubjectRow {
  rowSeq += 1;
  return { id: `stats-row-${rowSeq}`, subjectId: "", simulationName: "", response: 1, effectSize: undefined, weight: 1 };
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

const TISSUE_OPTIONS = [
  { value: "grey", label: "Grey matter" },
  { value: "white", label: "White matter" },
  { value: "all", label: "All tissue" },
];
const SPACE_OPTIONS = [
  { value: "mni", label: "MNI volume" },
  { value: "fsaverage", label: "fsaverage surface" },
];
const CLUSTER_STAT_OPTIONS = [
  { value: "mass", label: "Mass (sum of t-values)" },
  { value: "size", label: "Size (voxel count)" },
];
const TEST_TYPE_OPTIONS = [
  { value: "unpaired", label: "Unpaired" },
  { value: "paired", label: "Paired" },
];
const ALTERNATIVE_OPTIONS = [
  { value: "two-sided", label: "Two-sided" },
  { value: "greater", label: "Greater" },
  { value: "less", label: "Less" },
];
const CORRELATION_TYPE_OPTIONS = [
  { value: "pearson", label: "Pearson" },
  { value: "spearman", label: "Spearman" },
];

/** A permutation test over one subject is not a test (the page's own rule, unchanged). */
const MIN_PARTICIPANTS = 2;

/** Why one row cannot take part — the noun phrases `SubjectsField` uses, in row order. */
function rowEligibility(mode: Mode) {
  return (row: SubjectRow): { ok: boolean; reason?: string } => {
    if (!row.subjectId) return { ok: false, reason: "no subject chosen" };
    if (!row.simulationName) return { ok: false, reason: "no simulation chosen" };
    if (mode === "correlation" && row.effectSize === undefined) return { ok: false, reason: "no effect size" };
    return { ok: true };
  };
}

function ClusterPermutationPanel() {
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  usePageScrollMemory();
  const jobs = useExtensionJobs();
  const [mode, setMode] = usePageSession<Mode>("mode", "classification");
  const [rows, setRows] = usePageSession<SubjectRow[]>("rows", () => [newRow(), newRow()]);
  const [analysisName, setAnalysisName] = usePageSession("analysisName", "");

  // shared advanced settings
  const [clusterThreshold, setClusterThreshold] = usePageSession<number | undefined>("advanced.clusterThreshold", 0.05);
  const [clusterStat, setClusterStat] = usePageSession("advanced.clusterStat", "mass");
  const [nPermutations, setNPermutations] = usePageSession<number | undefined>("advanced.nPermutations", 1000);
  const [alpha, setAlpha] = usePageSession<number | undefined>("advanced.alpha", 0.05);
  const [nJobs, setNJobs] = usePageSession<number | undefined>("advanced.nJobs", -1);
  const [tissueType, setTissueType] = usePageSession("advanced.tissueType", "grey");
  const [niftiPattern, setNiftiPattern] = usePageSession("advanced.niftiPattern", "");
  const [space, setSpace] = usePageSession("advanced.space", "mni");
  const [fsaverageField, setFsaverageField] = usePageSession("advanced.fsaverageField", "TI_max");
  const [fsaverageSpacing, setFsaverageSpacing] = usePageSession<number | undefined>("advanced.fsaverageSpacing", 5);
  const [atlasFiles, setAtlasFiles] = usePageSession("advanced.atlasFiles", "");

  // classification-only
  const [testType, setTestType] = usePageSession("classification.testType", "unpaired");
  const [alternative, setAlternative] = usePageSession("classification.alternative", "two-sided");
  const [group1Name, setGroup1Name] = usePageSession("classification.group1Name", "Responders");
  const [group2Name, setGroup2Name] = usePageSession("classification.group2Name", "Non-Responders");
  const [valueMetric, setValueMetric] = usePageSession("classification.valueMetric", "Current intensity");

  // correlation-only
  const [correlationType, setCorrelationType] = usePageSession("correlation.type", "pearson");
  const [useWeights, setUseWeights] = usePageSession("correlation.useWeights", true);
  const [effectMetric, setEffectMetric] = usePageSession("correlation.effectMetric", "Effect size");
  const [fieldMetric, setFieldMetric] = usePageSession("correlation.fieldMetric", "Electric field magnitude");

  const [submitting, setSubmitting] = useState(false);

  const simQueries = useQueries({ queries: rows.map((r) => ({ queryKey: ["simulations", r.subjectId], queryFn: () => getSimulationsFor(r.subjectId), enabled: !!r.subjectId })) });
  const subjectOptions = (subjectsQuery.data ?? []).map((s) => ({ value: s.id, label: s.id }));

  function updateRow(id: string, patch: Partial<SubjectRow>) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((prev) => [...prev, newRow()]);
  }
  function removeRow(id: string) {
    setRows((prev) => prev.filter((r) => r.id !== id));
  }

  const validRows = rows.filter((r) => r.subjectId && r.simulationName);
  const atlasList = atlasFiles
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  // One sentence for the participants table, from the shared model, and it names the row it means
  // — the same mechanism `SubjectsField` gives the run pages (J3/D5).
  const participantsBlocked = participantsBlockedReason(
    validRows.length,
    blockedParticipants(rows, rowEligibility(mode)),
    MIN_PARTICIPANTS,
  );
  const clientErrors: string[] = [];
  if (participantsBlocked) clientErrors.push(participantsBlocked);
  if (!analysisName.trim()) clientErrors.push("Enter an analysis name.");
  if (mode === "classification" && validRows.length >= 2) {
    const responses = new Set(validRows.map((r) => r.response));
    if (!(responses.has(0) && responses.has(1))) clientErrors.push("Classification needs at least one subject in each response group.");
  }

  const shared: SharedStatsFields = {
    analysisName: analysisName.trim(),
    clusterThreshold: clusterThreshold ?? 0.05,
    clusterStat: clusterStat as "mass" | "size",
    nPermutations: nPermutations ?? 1000,
    alpha: alpha ?? 0.05,
    nJobs: nJobs ?? -1,
    tissueType: tissueType as "grey" | "white" | "all",
    niftiPattern,
    space: space as "mni" | "fsaverage",
    fsaverageField,
    fsaverageSpacing: fsaverageSpacing ?? 5,
    atlasFiles: atlasList,
  };
  const config: GroupComparisonConfig | CorrelationConfig | null =
    clientErrors.length > 0
      ? null
      : mode === "classification"
        ? buildGroupComparisonConfig(
            shared,
            validRows.map((r) => ({ subjectId: r.subjectId, simulationName: r.simulationName, response: r.response })),
            { testType: testType as "unpaired" | "paired", alternative: alternative as "two-sided" | "greater" | "less", group1Name, group2Name, valueMetric },
          )
        : buildCorrelationConfig(
            shared,
            validRows.map((r) => ({ subjectId: r.subjectId, simulationName: r.simulationName, effectSize: r.effectSize ?? 0, weight: r.weight ?? 1 })),
            { correlationType: correlationType as "pearson" | "spearman", useWeights, effectMetric, fieldMetric },
          );

  const subjectIds = [...new Set(validRows.map((r) => r.subjectId))];
  const debouncedKey = useDebounced(config ? JSON.stringify({ config, subjectIds }) : "", 400);
  const validateQuery = useQuery({
    queryKey: ["validate-stats", debouncedKey],
    queryFn: () => validateStats((JSON.parse(debouncedKey) as { config: GroupComparisonConfig | CorrelationConfig }).config),
    enabled: debouncedKey !== "",
  });
  const planQuery = useQuery({
    queryKey: ["plan-stats", debouncedKey],
    queryFn: () => {
      const parsed = JSON.parse(debouncedKey) as { config: GroupComparisonConfig | CorrelationConfig; subjectIds: string[] };
      return planStats(parsed.config, parsed.subjectIds);
    },
    enabled: debouncedKey !== "" && validateQuery.data?.ok === true,
  });

  const serverErrors = validateQuery.data?.errors.map((e) => `${e.path ? `${e.path}: ` : ""}${e.message}`) ?? [];

  function handleRunClick() {
    if (!config) {
      notify.error(clientErrors[0] ?? "Complete the analysis configuration before running.");
      return;
    }
    void run();
  }

  async function run() {
    if (!config) return;
    setSubmitting(true);
    try {
      const job = await createStatsJob(config, subjectIds);
      jobs.trackJob(job);
      notify.success(`Queued: ${mode === "classification" ? "group comparison" : "correlation"} "${analysisName.trim()}"`);
    } catch {
      notify.error("Could not queue the analysis.");
    } finally {
      setSubmitting(false);
    }
  }

  const digest = panelDigest(clientErrors, planQuery.data, config !== null && (validateQuery.isPending || planQuery.isFetching));

  return (
    <PageLayout
      rightPane={<ExtensionRunPanel kind="stats" subjects={subjectIds} {...jobs} plan={
        <PlanSummary
            plan={planQuery.data}
            loading={config !== null && (validateQuery.isPending || planQuery.isFetching)}
            error={validateQuery.error || planQuery.error ? "Could not compute the plan." : undefined}
            serverErrors={serverErrors}
            idleMessage="Complete the analysis configuration to see its plan."
          />
      } />}
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
      <div className="panel-page extension-inputs">
        <Card>
          <CardBody>
            <Field label="Analysis type">
              <SegmentedControl
                aria-label="Analysis type"
                value={mode}
                onValueChange={(v) => setMode(v as Mode)}
                options={[
                  { value: "classification", label: "Classification" },
                  { value: "correlation", label: "Correlation" },
                ]}
              />
            </Field>
          </CardBody>
        </Card>

        <div className="panel-page-split">
          <div className="panel-page-col">
            <ParticipantsField
              rows={rows}
              rowId={(r) => r.id}
              subjectOf={(r) => r.subjectId}
              eligibility={rowEligibility(mode)}
              note="one job over all subjects"
              onAdd={addRow}
              onRemove={removeRow}
              loading={subjectsQuery.isPending}
              help={
                <HelpIcon title="Cluster permutation" label="About this page" text="Compare or correlate field intensities across subjects with permutation testing." />
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
              columns={
                mode === "classification"
                  ? [
                      {
                        id: "response",
                        header: "Response",
                        cell: (row) => (
                          <Select
                            value={String(row.response)}
                            onValueChange={(v) => updateRow(row.id, { response: Number(v) as 0 | 1 })}
                            options={[
                              { value: "1", label: "Responder" },
                              { value: "0", label: "Non-responder" },
                            ]}
                          />
                        ),
                      },
                    ]
                  : [
                      {
                        id: "effect",
                        header: "Effect size",
                        cell: (row, i) => (
                          <NumberInput
                            value={row.effectSize}
                            onValueChange={(v) => updateRow(row.id, { effectSize: v })}
                            placeholder="Effect size"
                            aria-label={`Effect size for row ${i + 1}`}
                          />
                        ),
                      },
                      {
                        id: "weight",
                        header: "Weight",
                        cell: (row, i) => (
                          <NumberInput
                            value={row.weight}
                            onValueChange={(v) => updateRow(row.id, { weight: v })}
                            placeholder="Weight"
                            step={0.1}
                            disabled={!useWeights}
                            aria-label={`Weight for row ${i + 1}`}
                          />
                        ),
                      },
                    ]
              }
            />
          </div>
          <div className="panel-page-col">

        <Card>
          <CardHeader title="Analysis" />
          <CardBody>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <Field label="Analysis name" htmlFor="cbp-analysis-name" required>
                <TextInput id="cbp-analysis-name" value={analysisName} onChange={(e) => setAnalysisName(e.target.value)} />
              </Field>
              {mode === "classification" ? (
                <div className="form-grid">
                  <Field label="Test type" htmlFor="cbp-test-type">
                    <Select id="cbp-test-type" value={testType} onValueChange={setTestType} options={TEST_TYPE_OPTIONS} />
                  </Field>
                  <Field label="Alternative" htmlFor="cbp-alternative">
                    <Select id="cbp-alternative" value={alternative} onValueChange={setAlternative} options={ALTERNATIVE_OPTIONS} />
                  </Field>
                  <Field label="Group 1 name" htmlFor="cbp-group1-name">
                    <TextInput id="cbp-group1-name" value={group1Name} onChange={(e) => setGroup1Name(e.target.value)} />
                  </Field>
                  <Field label="Group 2 name" htmlFor="cbp-group2-name">
                    <TextInput id="cbp-group2-name" value={group2Name} onChange={(e) => setGroup2Name(e.target.value)} />
                  </Field>
                  <Field label="Value metric label" htmlFor="cbp-value-metric">
                    <TextInput id="cbp-value-metric" value={valueMetric} onChange={(e) => setValueMetric(e.target.value)} />
                  </Field>
                </div>
              ) : (
                <div className="form-grid">
                  <Field label="Correlation type" htmlFor="cbp-correlation-type">
                    <Select id="cbp-correlation-type" value={correlationType} onValueChange={setCorrelationType} options={CORRELATION_TYPE_OPTIONS} />
                  </Field>
                  <Field label="Effect metric label" htmlFor="cbp-effect-metric">
                    <TextInput id="cbp-effect-metric" value={effectMetric} onChange={(e) => setEffectMetric(e.target.value)} />
                  </Field>
                  <Field label="Field metric label" htmlFor="cbp-field-metric">
                    <TextInput id="cbp-field-metric" value={fieldMetric} onChange={(e) => setFieldMetric(e.target.value)} />
                  </Field>
                  <div style={{ display: "flex", alignItems: "flex-end", paddingBottom: 6 }}>
                    <Checkbox checked={useWeights} onCheckedChange={setUseWeights} label="Apply per-subject weights" />
                  </div>
                </div>
              )}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Advanced" />
          <CardBody>
            <div className="form-grid">
              <Field label="Cluster threshold" htmlFor="cbp-cluster-threshold" help="Uncorrected p-value threshold for forming clusters.">
                <NumberInput id="cbp-cluster-threshold" value={clusterThreshold} onValueChange={setClusterThreshold} min={0} max={1} step={0.01} />
              </Field>
              <Field label="Cluster statistic" htmlFor="cbp-cluster-stat">
                <Select id="cbp-cluster-stat" value={clusterStat} onValueChange={setClusterStat} options={CLUSTER_STAT_OPTIONS} />
              </Field>
              <Field label="Permutations" htmlFor="cbp-n-permutations">
                <NumberInput id="cbp-n-permutations" value={nPermutations} onValueChange={setNPermutations} min={100} step={100} />
              </Field>
              <Field label="Alpha" htmlFor="cbp-alpha" help="Family-wise error rate for significance.">
                <NumberInput id="cbp-alpha" value={alpha} onValueChange={setAlpha} min={0} max={1} step={0.01} />
              </Field>
              <Field label="Parallel workers" htmlFor="cbp-n-jobs" help="-1 uses all CPUs.">
                <NumberInput id="cbp-n-jobs" value={nJobs} onValueChange={setNJobs} step={1} />
              </Field>
              <Field label="Tissue" htmlFor="cbp-tissue-type">
                <Select id="cbp-tissue-type" value={tissueType} onValueChange={setTissueType} options={TISSUE_OPTIONS} />
              </Field>
              <Field label="NIfTI file pattern" htmlFor="cbp-nifti-pattern" help="Leave blank to derive automatically from the tissue type.">
                <TextInput id="cbp-nifti-pattern" value={niftiPattern} onChange={(e) => setNiftiPattern(e.target.value)} />
              </Field>
              <Field label="Space" htmlFor="cbp-space">
                <Select id="cbp-space" value={space} onValueChange={setSpace} options={SPACE_OPTIONS} />
              </Field>
              {space === "fsaverage" && (
                <>
                  <Field label="fsaverage field" htmlFor="cbp-fsaverage-field">
                    <TextInput id="cbp-fsaverage-field" value={fsaverageField} onChange={(e) => setFsaverageField(e.target.value)} />
                  </Field>
                  <Field label="fsaverage spacing" htmlFor="cbp-fsaverage-spacing">
                    <NumberInput id="cbp-fsaverage-spacing" value={fsaverageSpacing} onValueChange={setFsaverageSpacing} min={5} max={7} step={1} />
                  </Field>
                </>
              )}
              <Field label="Atlas files" htmlFor="cbp-atlas-files" help="Comma-separated atlas filenames for overlap analysis (optional).">
                <TextInput id="cbp-atlas-files" value={atlasFiles} onChange={(e) => setAtlasFiles(e.target.value)} placeholder="e.g. HarvardOxford-cort-maxprob-thr25.nii.gz" />
              </Field>
            </div>
          </CardBody>
        </Card>


          </div>
        </div>
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "panel-cluster-permutation",
  title: "Cluster permutation",
  purpose: "Compare or correlate field intensities across subjects with permutation testing.",
  navGroup: "panels",
  order: 105,
  icon: GitCompare,
  Component: ClusterPermutationPanel,
  enabled: isPanelEnabled("cluster-permutation"),
};

export default page;
