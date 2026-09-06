import { useEffect, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Image as ImageIcon, Play, Info } from "lucide-react";
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
import { Button, IconButton } from "../../../ui/Button";
import { Tooltip } from "../../../ui/Overlay";
import { notify } from "../../../ui/Toast";
import { ActionBar } from "../../../ui/Chrome";
import { isPanelEnabled, panelDigest } from "../_shared";
import "../panels.css";
import { PlanSummary } from "../PlanSummary";
import { createNilearnJob, getSimulationsFor, planNilearn, validateNilearn } from "./api";
import { buildNilearnConfig, type NilearnPair } from "./config";

const ATLAS_OPTIONS = [
  { value: "harvard_oxford_sub", label: "Harvard-Oxford (subcortical)" },
  { value: "harvard_oxford", label: "Harvard-Oxford" },
  { value: "aal", label: "AAL" },
  { value: "schaefer_2018", label: "Schaefer 2018" },
];
const REGION_OPTIONS = [{ value: "__all__", label: "All regions" }];

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
  const [pairs, setPairs] = usePageSession<Pair[]>("pairs", () => [newPair()]);
  const [subdir, setSubdir] = usePageSession("subdir", "");
  const [usePercentiles, setUsePercentiles] = usePageSession("usePercentiles", false);
  const [minCutoff, setMinCutoff] = usePageSession<number | undefined>("minCutoff", 0.3);
  const [maxCutoff, setMaxCutoff] = usePageSession<number | undefined>("maxCutoff", 5.0);
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
          minCutoff: minCutoff ?? 0,
          maxCutoff: maxCutoff ?? 0,
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
      await createNilearnJob(config, subjectIds);
      notify.success(`Queued: Nilearn visuals → nilearn_visuals/${config.subdir_name}`);
    } catch {
      notify.error("Could not queue the visualization job.");
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
            <Button variant="primary" icon={<Play size={14} />} loading={submitting} onClick={handleRunClick} data-testid="run-button">
              Generate images
            </Button>
          }
        />
      }
    >
      <div className="panel-page">
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
              fill
              loading={subjectsQuery.isPending}
              help={
                <>
                  <Tooltip label="Create Nilearn high-resolution publication visualizations.">
                    <IconButton icon={<Info size={13} />} aria-label="About this page" variant="ghost" size="sm" />
                  </Tooltip>
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
                  onCheckedChange={setUsePercentiles}
                  label="Use percentile cutoffs — cutoff values are treated as percentiles (0–100%) of the maximum field value"
                />
                <div className="form-grid">
                  <Field label={usePercentiles ? "Minimum cutoff (%)" : "Minimum cutoff"} htmlFor="nilearn-min-cutoff">
                    <NumberInput id="nilearn-min-cutoff" value={minCutoff} onValueChange={setMinCutoff} min={0} max={usePercentiles ? 100 : 10} step={usePercentiles ? 1 : 0.1} unit={usePercentiles ? "%" : "V/m"} />
                  </Field>
                  <Field label="Atlas selection" htmlFor="nilearn-atlas">
                    <Select id="nilearn-atlas" value={atlas} onValueChange={setAtlas} options={ATLAS_OPTIONS} />
                  </Field>
                  <Field label={usePercentiles ? "Maximum cutoff (%)" : "Maximum cutoff"} htmlFor="nilearn-max-cutoff">
                    <NumberInput id="nilearn-max-cutoff" value={maxCutoff} onValueChange={setMaxCutoff} min={0} max={usePercentiles ? 100 : 50} step={usePercentiles ? 1 : 0.5} unit={usePercentiles ? "%" : "V/m"} />
                  </Field>
                  <Field label="Region selection" htmlFor="nilearn-region">
                    <Select id="nilearn-region" value={region} onValueChange={setRegion} options={REGION_OPTIONS} />
                  </Field>
                </div>
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
              problems={clientErrors}
              idleMessage="Complete the configuration above to see its plan."
            />
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
