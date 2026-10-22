import { useEffect, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Image as ImageIcon, Play } from "lucide-react";
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
import { Button } from "../../../ui/Button";
import { HelpIcon } from "../../../ui/HelpPopover";
import { notify, notifySubmitError } from "../../../ui/Toast";
import { ActionBar } from "../../../ui/Chrome";
import { isPanelEnabled, panelDigest } from "../_shared";
import "../panels.css";
import { PlanSummary } from "../PlanSummary";
import { ExtensionRunPanel, useExtensionJobs } from "../ExtensionRunPanel";
import { createNilearnJob, getSimulationsFor, planNilearn, validateNilearn } from "./api";
import { buildNilearnConfig, type NilearnPair } from "./config";

const ATLAS_OPTIONS = [
  { value: "harvard_oxford_sub", label: "Harvard-Oxford (subcortical)" },
  { value: "harvard_oxford", label: "Harvard-Oxford (cortical)" },
  { value: "aal", label: "AAL3" },
  { value: "schaefer_2018", label: "Schaefer 2018 (100 parcels)" },
];
const REGION_OPTIONS = [{ value: "__all__", label: "All regions" }];
const CUTOFF_HELP =
  "Field values below the minimum are hidden; the colour scale tops out at the maximum. Leave a cutoff empty to take it from the averaged field: the 95th percentile (minimum) and 99.9th percentile (maximum) of its non-zero voxels.";

/** One pair is a complete visualisation; more are averaged together (the page's own rule). */
const MIN_PARTICIPANTS = 1;

/** Why one row cannot take part — the noun phrases `SubjectsField` uses, in row order. */
function rowEligibility(row: Pair): { ok: boolean; reason?: string } {
  if (!row.subjectId) return { ok: false, reason: "no subject chosen" };
  if (!row.simulationName) return { ok: false, reason: "no simulation chosen" };
  return { ok: true };
}

interface Pair extends NilearnPair {
  id: string;
}

let pairSeq = 0;
function newPair(): Pair {
  pairSeq += 1;
  return { id: `pair-${pairSeq}`, subjectId: "", simulationName: "" };
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

function NilearnVisualsPanel() {
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });
  usePageScrollMemory();
  const jobs = useExtensionJobs();
  const [pairs, setPairs] = usePageSession<Pair[]>("pairs", () => [newPair()]);
  const [subdir, setSubdir] = usePageSession("subdir", "");
  const [usePercentiles, setUsePercentiles] = usePageSession("usePercentiles", false);
  // Empty = the job derives the range from the field itself (95th–99.9th percentile). A fixed
  // V/m default cannot work: TI fields peak near 0.1–0.3 V/m, so the former 0.3 drew blank PDFs.
  const [minCutoff, setMinCutoff] = usePageSession<number | undefined>("minCutoff", undefined);
  const [maxCutoff, setMaxCutoff] = usePageSession<number | undefined>("maxCutoff", undefined);
  const [atlas, setAtlas] = usePageSession("atlas", "harvard_oxford_sub");
  const [region, setRegion] = usePageSession("region", "__all__");
  const [submitting, setSubmitting] = useState(false);

  const simQueries = useQueries({ queries: pairs.map((p) => ({ queryKey: ["simulations", p.subjectId], queryFn: () => getSimulationsFor(p.subjectId), enabled: !!p.subjectId })) });
  const subjectOptions = (subjectsQuery.data ?? []).map((s) => ({ value: s.id, label: s.id }));

  function updatePair(id: string, patch: Partial<Pair>) {
    setPairs((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  }
  function addPair() {
    setPairs((prev) => [...prev, newPair()]);
  }
  function removePair(id: string) {
    setPairs((prev) => prev.filter((p) => p.id !== id));
  }
  function clearAll() {
    setPairs([newPair()]);
  }

  const validPairs = pairs.filter((p) => p.subjectId && p.simulationName);
  // One sentence for the participants table, from the shared model, and it names the row it means
  // — the same mechanism `SubjectsField` gives the run pages (J3/D5).
  const participantsBlocked = participantsBlockedReason(
    validPairs.length,
    blockedParticipants(pairs, rowEligibility),
    MIN_PARTICIPANTS,
  );
  const clientErrors: string[] = [];
  if (participantsBlocked) clientErrors.push(participantsBlocked);
  if (!subdir.trim()) clientErrors.push("Enter a sub-directory name for the output files.");

  const config =
    clientErrors.length === 0
      ? buildNilearnConfig({
          pairs: validPairs,
          subdirName: subdir.trim(),
          usePercentiles,
          minCutoff,
          maxCutoff,
          atlasName: atlas,
          selectedRegion: region,
        })
      : null;
  const subjectIds = [...new Set(validPairs.map((p) => p.subjectId))];

  const debouncedKey = useDebounced(config ? JSON.stringify({ config, subjectIds }) : "", 350);
  const validateQuery = useQuery({
    queryKey: ["validate-nilearn", debouncedKey],
    queryFn: () => validateNilearn(JSON.parse(debouncedKey).config),
    enabled: debouncedKey !== "",
  });
  const planQuery = useQuery({
    queryKey: ["plan-nilearn", debouncedKey],
    queryFn: () => {
      const parsed = JSON.parse(debouncedKey) as { config: ReturnType<typeof buildNilearnConfig>; subjectIds: string[] };
      return planNilearn(parsed.config, parsed.subjectIds);
    },
    enabled: debouncedKey !== "" && validateQuery.data?.ok === true,
  });

  const serverErrors = validateQuery.data?.errors.map((e) => `${e.path ? `${e.path}: ` : ""}${e.message}`) ?? [];

  function handleRunClick() {
    if (!config) {
      notify.error(clientErrors[0] ?? "Complete the configuration before running.");
      return;
    }
    void run();
  }

  async function run() {
    if (!config) return;
    setSubmitting(true);
    try {
      const job = await createNilearnJob(config, subjectIds);
      jobs.trackJob(job);
      notify.success(`Queued: Nilearn visuals → nilearn_visuals/${config.subdir_name}`);
    } catch (error) {
      notifySubmitError("Could not queue the visualization job.", error);
    } finally {
      setSubmitting(false);
    }
  }

  const digest = panelDigest(clientErrors, planQuery.data, config !== null && (validateQuery.isPending || planQuery.isFetching));

  return (
    <PageLayout
      rightPane={<ExtensionRunPanel kind="nilearn" subjects={subjectIds} {...jobs} plan={
        <PlanSummary
              plan={planQuery.data}
              loading={config !== null && (validateQuery.isPending || planQuery.isFetching)}
              error={validateQuery.error || planQuery.error ? "Could not compute the plan." : undefined}
              serverErrors={serverErrors}
              idleMessage="Complete the configuration to see its plan."
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
              Generate images
            </Button>
          }
        />
      }
    >
      <div className="panel-page extension-inputs">
        <div className="panel-page-split">
          <div className="panel-page-col">
            <ParticipantsField
              rows={pairs}
              rowId={(p) => p.id}
              subjectOf={(p) => p.subjectId}
              eligibility={rowEligibility}
              note="one job over all subjects"
              onAdd={addPair}
              addLabel="Add pair"
              onRemove={removePair}
              loading={subjectsQuery.isPending}
              help={
                <>
                  <HelpIcon title="Nilearn visuals" label="About this page" text="Averages the chosen simulations' MNI grey-matter fields (TI or mTI) and saves a multi-slice PDF with atlas outlines and a glass-brain PDF to derivatives/ti-toolbox/nilearn_visuals/{name}/." />
                  <Button variant="ghost" size="sm" onClick={clearAll}>
                    Clear all
                  </Button>
                </>
              }
              subjectCell={(pair) => (
                <Select
                  value={pair.subjectId || undefined}
                  onValueChange={(v) => updatePair(pair.id, { subjectId: v, simulationName: "" })}
                  options={subjectOptions}
                  placeholder="Subject"
                />
              )}
              simulationCell={(pair, i) => (
                <Select
                  value={pair.simulationName || undefined}
                  onValueChange={(v) => updatePair(pair.id, { simulationName: v })}
                  options={(simQueries[i]?.data ?? []).map((s) => ({ value: s.name, label: s.name }))}
                  placeholder={pair.subjectId ? "Simulation" : "Pick a subject first"}
                  disabled={!pair.subjectId}
                />
              )}
              columns={[]}
            />
          </div>
          <div className="panel-page-col">

          <Card>
            <CardHeader title="Output" />
            <CardBody>
              <Field label="Sub-directory name" htmlFor="nilearn-subdir" help="Files are saved to derivatives/ti-toolbox/nilearn_visuals/{name}/.">
                <TextInput id="nilearn-subdir" value={subdir} placeholder="e.g. thalamus_montage_v1" onChange={(e) => setSubdir(e.target.value)} />
              </Field>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Visualization parameters" />
            <CardBody>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                <Checkbox
                  checked={usePercentiles}
                  onCheckedChange={(on) => {
                    // A number typed in one unit means nothing in the other.
                    setUsePercentiles(on);
                    setMinCutoff(undefined);
                    setMaxCutoff(undefined);
                  }}
                  label="Give cutoffs as percentiles (0–100) of the field's non-zero voxels instead of V/m"
                />
                <div className="form-grid">
                  <Field label={usePercentiles ? "Minimum cutoff (%)" : "Minimum cutoff"} htmlFor="nilearn-min-cutoff" help={CUTOFF_HELP}>
                    <NumberInput id="nilearn-min-cutoff" value={minCutoff} onValueChange={setMinCutoff} placeholder="auto (p95)" min={0} max={usePercentiles ? 100 : 10} step={usePercentiles ? 1 : 0.01} unit={usePercentiles ? "%" : "V/m"} />
                  </Field>
                  <Field label="Atlas selection" htmlFor="nilearn-atlas" help="Region outlines drawn over the field on the slice PDF. The atlases ship with TI-Toolbox, so no download is needed.">
                    <Select id="nilearn-atlas" value={atlas} onValueChange={setAtlas} options={ATLAS_OPTIONS} />
                  </Field>
                  <Field label={usePercentiles ? "Maximum cutoff (%)" : "Maximum cutoff"} htmlFor="nilearn-max-cutoff" help={CUTOFF_HELP}>
                    <NumberInput id="nilearn-max-cutoff" value={maxCutoff} onValueChange={setMaxCutoff} placeholder="auto (p99.9)" min={0} max={usePercentiles ? 100 : 10} step={usePercentiles ? 1 : 0.01} unit={usePercentiles ? "%" : "V/m"} />
                  </Field>
                  <Field label="Region selection" htmlFor="nilearn-region" help="Every region of the chosen atlas is outlined. Outlining only some regions is not available here yet.">
                    <Select id="nilearn-region" value={region} onValueChange={setRegion} options={REGION_OPTIONS} />
                  </Field>
                </div>
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
  id: "panel-nilearn-visuals",
  title: "Nilearn visuals",
  purpose: "Create Nilearn high-resolution publication visualizations.",
  navGroup: "panels",
  order: 120,
  icon: ImageIcon,
  Component: NilearnVisualsPanel,
  enabled: isPanelEnabled("nilearn-visuals"),
};

export default page;
