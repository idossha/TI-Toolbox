/**
 * 3D Visual Exporter — the v3 migration of the v2.5.0 `tit/gui/extensions/visual_exporter.py`
 * (removed in v3.0.0; see git tag v2.5.0).
 *
 * Two things changed and nothing else did. First, the export is a **job**: 2.5.0 ran cortical
 * regions / vectors / montage as an ad-hoc `QThread` subprocess and ran the sub-cortical mode
 * *inline on the Qt main thread*, so a long export froze the window and neither left a trace
 * anywhere. Every mode here submits a `blender` job, so it appears in the Jobs rail and the
 * terminal like every other computation, and Stop lives where Stop always lives.
 *
 * Second, region picking follows the one selection grammar (`ui/SelectionList`'s
 * `SelectionPicker`) instead of a bare multi-select `QListWidget` with its own "Select all /
 * Clear / Search" row.
 *
 * What deliberately did *not* change: the config each mode builds. `config.ts` sets exactly the
 * fields `_run` set, including the ones the Qt widget hardcoded, so the files written are
 * byte-identical to 2.5.0's.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Boxes, Play } from "lucide-react";
import type { PageDef } from "../../../app/registry";
import { usePageSession } from "../../../app/pageSession";
import { getSubjects } from "../../../api/client";
import { Card, CardBody, CardHeader, PageLayout, PaneHeaderControls, usePaneController } from "../../../ui/Layout";
import { usePageScrollMemory } from "../../_shared/session/usePageScrollMemory";
import { Field, TextInput } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { NumberInput } from "../../../ui/NumberInput";
import { Checkbox } from "../../../ui/Toggle";
import { SegmentedControl } from "../../../ui/SegmentedControl";
import { SelectionPicker, type SelectionItem } from "../../../ui/SelectionList";
import { Button } from "../../../ui/Button";
import { HelpIcon } from "../../../ui/HelpPopover";
import { notify, notifySubmitError } from "../../../ui/Toast";
import { ActionBar } from "../../../ui/Chrome";
import { isPanelEnabled, panelDigest } from "../_shared";
import "../panels.css";
import { PlanSummary } from "../PlanSummary";
import { ExtensionRunPanel, useExtensionJobs } from "../ExtensionRunPanel";
import { ExistingOutputsDialog, isExistingOutputsConflict } from "../../_shared/run/ExistingOutputsDialog";
import { emptyRoi, type NetworkRoiValue, type RoiValue } from "../../_shared/roi/types";
import { NetworkChooser, autoNetworkName, networkSelection, pairTotals, presetTotals, getTractEdges, getTractConnections, getTractPresets, type TractConnection, type TractPreset } from "../../_shared/roi";
import { AssessNetworks } from "./AssessNetworks";
import { OwnNetworkPicker } from "./OwnNetworkPicker";
import { NetworkAdvanced, type NetworkSetupRecord } from "./NetworkSetup";
import { isPicture, NetworkRenders } from "./NetworkRenders";
import { ExportPreview } from "./ExportPreview";
import { readExportMontage } from "./previewModel";
import { getTextFile } from "../../results/api";
import { createBlenderJob, createTractJob, getAtlasRegions, getNiftiLabels, getSimulationNetworks, getSimulationsFor, planBlender, validateBlender, type BlenderConfig } from "./api";
import {
  assessState,
  buildMontageConfig,
  buildNetworkAssessConfig,
  buildNetworkConfig,
  buildOwnAssessConfig,
  bundleName,
  buildRegionConfigs,
  buildSubcorticalConfig,
  buildVectorConfig,
  networkPlanLine,
  CHOOSE_A_FILE,
  CHOOSE_A_NETWORK,
  NO_RECORDED_NET,
  outputHint,
  PERCENTILE_ORDER,
  parseLabels,
  type Mode,
  type NetworksForm,
} from "./config";

const MODE_OPTIONS: { value: Mode; label: string }[] = [
  { value: "regions", label: "Cortical regions" },
  { value: "vectors", label: "Field vectors" },
  { value: "montage", label: "Montage visualizer" },
  { value: "subcortical", label: "Sub-cortical" },
  { value: "networks", label: "Networks" },
];

const NETWORK_METRIC_OPTIONS = [
  { value: "direction", label: "Fibre direction (RGB)" },
  { value: "ti_max", label: "TI_max" },
];
const NETWORK_QUALITY_OPTIONS = [
  { value: "preview", label: "Fast preview" },
  { value: "final", label: "Final" },
];
const FRESH_NETWORK: NetworkRoiValue = { ...(emptyRoi("network") as NetworkRoiValue), how: "preset" };

/** The two atlases the Qt combo offered (`const.ATLAS_DK40`, `const.ATLAS_A2009S`). */
const ATLAS_OPTIONS = [
  { value: "DK40", label: "DK40" },
  { value: "a2009s", label: "a2009s" },
];

const ANCHOR_OPTIONS = [
  { value: "tail", label: "Tail" },
  { value: "head", label: "Head" },
];
const COLOR_OPTIONS = [
  { value: "rgb", label: "RGB (per channel)" },
  { value: "magscale", label: "Magnitude scale" },
];

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

function VisualExporterPanel() {
  usePageScrollMemory();
  const jobs = useExtensionJobs();
  const scenePane = usePaneController({ pageId: "panel-visual-exporter", name: "run" });
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: () => getSubjects() });

  const [mode, setMode] = usePageSession<Mode>("mode", "regions");
  const [subjectId, setSubjectId] = usePageSession("subjectId", "");
  const [simulationName, setSimulationName] = usePageSession("simulationName", "");

  // Cortical regions
  const [atlas, setAtlas] = usePageSession("atlas", "DK40");
  const [regionField, setRegionField] = usePageSession("regionField", "TI_max");
  const [regions, setRegions] = usePageSession<string[]>("regions", []);

  // Field vectors
  const [lengthScale, setLengthScale] = usePageSession<number | undefined>("lengthScale", 1.0);
  const [vectorWidth, setVectorWidth] = usePageSession<number | undefined>("vectorWidth", 1.0);
  const [anchor, setAnchor] = usePageSession("anchor", "tail");
  const [color, setColor] = usePageSession("color", "rgb");
  const [bluePct, setBluePct] = usePageSession<number | undefined>("bluePct", 50);
  const [greenPct, setGreenPct] = usePageSession<number | undefined>("greenPct", 80);
  const [redPct, setRedPct] = usePageSession<number | undefined>("redPct", 95);
  const [seed, setSeed] = usePageSession<number | undefined>("seed", 42);
  const [count, setCount] = usePageSession<number | undefined>("count", 10000);
  const [allNodes, setAllNodes] = usePageSession("allNodes", false);
  const [exportCh1Ch2, setExportCh1Ch2] = usePageSession("exportCh1Ch2", false);
  const [exportSum, setExportSum] = usePageSession("exportSum", false);
  const [exportTiNormal, setExportTiNormal] = usePageSession("exportTiNormal", false);

  // Montage visualizer
  const [montageOnly, setMontageOnly] = usePageSession("montageOnly", false);
  const [diameter, setDiameter] = usePageSession<number | undefined>("diameter", 10.0);
  const [height, setHeight] = usePageSession<number | undefined>("height", 6.0);

  // Sub-cortical
  const [niftiPath, setNiftiPath] = usePageSession("niftiPath", "");
  const [labelIds, setLabelIds] = usePageSession<string[]>("labelIds", []);
  const [labelsText, setLabelsText] = usePageSession("labelsText", "");
  const [cleanComponents, setCleanComponents] = usePageSession("cleanComponents", false);
  const [subcortField, setSubcortField] = usePageSession("subcortField", "TI_max");

  // Networks
  const [networkValue, setNetworkValue] = usePageSession<NetworkRoiValue>("networkValue", FRESH_NETWORK);
  const [networkOwnFile, setNetworkOwnFile] = usePageSession("networkOwnFile", false);
  const [ownNetwork, setOwnNetwork] = usePageSession("ownNetwork", "");
  const [networkOverrides, setNetworkOverrides] = usePageSession<Record<string, unknown>>("networkOverrides", {});
  const [networkMetric, setNetworkMetric] = usePageSession<NetworksForm["metric"]>("networkMetric", "direction");
  const [networkStills, setNetworkStills] = usePageSession("networkStills", true);
  const [networkTurntable, setNetworkTurntable] = usePageSession("networkTurntable", false);
  const [networkExportBlend, setNetworkExportBlend] = usePageSession("networkExportBlend", false);
  const [networkQuality, setNetworkQuality] = usePageSession<NetworksForm["quality"]>("networkQuality", "preview");

  const [submitting, setSubmitting] = useState(false);
  /** The jobs a 409 left unqueued, awaiting the existing-outputs decision. */
  const [refused, setRefused] = useState<BlenderConfig[] | null>(null);

  const simulationsQuery = useQuery({
    queryKey: ["simulations", subjectId],
    queryFn: () => getSimulationsFor(subjectId),
    enabled: !!subjectId,
  });
  const regionsQuery = useQuery({
    queryKey: ["atlas-regions", subjectId, atlas],
    queryFn: () => getAtlasRegions(subjectId, atlas),
    enabled: mode === "regions" && !!subjectId,
  });
  const networksQuery = useQuery({
    queryKey: ["simulation-networks", subjectId, simulationName],
    queryFn: () => getSimulationNetworks(subjectId, simulationName),
    enabled: mode === "networks" && !!subjectId && !!simulationName,
  });
  const onNetworkChange = (value: RoiValue) => setNetworkValue(value as NetworkRoiValue);
  // A chosen network is what this tab renders, unless the user's own file was asked for.
  const chooserActive = mode === "networks" && !networkOwnFile;
  const ownActive = mode === "networks" && networkOwnFile;
  const ownNeedsAssess = ownActive && !!ownNetwork && !!networksQuery.data && !networksQuery.data.own_assessed.includes(ownNetwork);
  const selection = useMemo(() => {
    if (!chooserActive || networkValue.pairs.length === 0) return null;
    const chosen = networkSelection(networkValue);
    return { ...chosen, name: bundleName(autoNetworkName(networkValue), chosen.pairs, networksQuery.data) };
  }, [chooserActive, networkValue, networksQuery.data]);
  // The count an assessed bundle must hold to be this network, from the same answer the picker shows.
  const countQuery = useQuery({
    queryKey: ["ve-network-count", subjectId, simulationName, networkValue.how, networkValue.preset, networkValue.includeOpposite, networkValue.pairs],
    enabled: chooserActive && networkValue.pairs.length > 0,
    queryFn: async (): Promise<number> => {
      if (networkValue.how === "preset") {
        const found = (await getTractPresets(subjectId)).find((p: TractPreset) => p.id === networkValue.preset);
        return found ? presetTotals(found, !!networkValue.includeOpposite).streamlines : 0;
      }
      const rows = networkValue.how === "strongest" ? await getTractConnections(subjectId, simulationName) : await getTractEdges(subjectId, networkValue.seeds);
      return pairTotals(rows as (TractConnection | { region_a: string; region_b: string; n: number })[], networkValue.pairs).streamlines;
    },
  });
  const assessing = selection && networksQuery.data && countQuery.data !== undefined ? assessState(selection, countQuery.data, networksQuery.data) : null;
  const simulationPath = simulationsQuery.data?.find((simulation) => simulation.name === simulationName)?.path;
  // The simulation's own record: the preview draws its montage from it, and Run refuses a
  // montage export of a simulation that recorded no net (montage_publication refuses it too).
  const montageQuery = useQuery({
    queryKey: ["export-montage", subjectId, simulationName, simulationPath],
    queryFn: async () => readExportMontage(await getTextFile(`${simulationPath}/documentation/config.json`)),
    enabled: mode === "montage" && !!subjectId && !!simulationPath,
    retry: false,
  });
  const labelsQuery = useQuery({
    queryKey: ["nifti-labels", subjectId, niftiPath],
    queryFn: () => getNiftiLabels(subjectId, niftiPath),
    enabled: mode === "subcortical" && !!subjectId,
    retry: false,
  });

  const subjectOptions = (subjectsQuery.data ?? []).map((s) => ({ value: s.id, label: s.id }));
  const simulationOptions = (simulationsQuery.data ?? []).map((s) => ({ value: s.name, label: s.name }));

  // `lh.insula` — the atlas key `RegionConfig.regions` is matched against
  // (`region_exporter._resolve_selected`) and the name each STL file takes.
  const regionItems: SelectionItem[] = useMemo(
    () =>
      (regionsQuery.data ?? []).map((r) => {
        const key = r.hemi ? `${r.hemi}.${r.name}` : r.name;
        return { id: key, label: key, detail: r.hemi ?? undefined };
      }),
    [regionsQuery.data],
  );

  const labelItems: SelectionItem[] = useMemo(
    () =>
      (labelsQuery.data ?? []).map((l) => ({
        id: String(l.id),
        label: l.name,
        // The id is what lands in `SubcorticalConfig.labels`, and the voxel count is what tells a
        // real structure from a stray label — both belong on the row, not just the name.
        detail: `${l.id} · ${l.n_voxels.toLocaleString()} voxels`,
        search: `${l.id} ${l.name}`,
      })),
    [labelsQuery.data],
  );
  // The browser answers for most subjects; when it cannot (no segmentation volume, or a path the
  // server will not read) the 2.5.0 text field is still the way through, rather than a dead end.
  const labelsBrowsable = labelsQuery.isSuccess && labelItems.length > 0;

  /** The Qt widget's own per-mode input rules, in its own order (`_run`'s first block). */
  const clientErrors: string[] = [];
  if (!subjectId) clientErrors.push("Select a subject.");
  else if (mode !== "subcortical" && !simulationName) clientErrors.push("Select a simulation.");
  else if (mode === "montage" && montageQuery.error?.message === NO_RECORDED_NET) clientErrors.push(NO_RECORDED_NET);
  // VectorConfig refuses a ramp whose thresholds do not rise; say so before the server does.
  if (mode === "vectors" && color === "magscale" && !((bluePct ?? 50) <= (greenPct ?? 80) && (greenPct ?? 80) <= (redPct ?? 95)))
    clientErrors.push(PERCENTILE_ORDER);
  if (mode === "networks" && clientErrors.length === 0) {
    if (networksQuery.isPending) clientErrors.push("Reading this simulation's network outputs…");
    else if (networksQuery.error) clientErrors.push(networksQuery.error.message);
    else if (ownActive && !ownNetwork) clientErrors.push(CHOOSE_A_FILE);
    else if (chooserActive && !selection) clientErrors.push(CHOOSE_A_NETWORK);
    else if (chooserActive && countQuery.error) clientErrors.push(countQuery.error.message);
    else if (chooserActive && assessing === null) clientErrors.push("Reading this network's streamline count…");
    else if (!networkStills && !networkTurntable) clientErrors.push("Choose a figure, a turntable or both.");
  }
  let subcorticalLabels: number[] = [];
  if (mode === "subcortical") {
    if (labelsBrowsable) {
      subcorticalLabels = labelIds.map(Number);
    } else {
      try {
        subcorticalLabels = parseLabels(labelsText);
      } catch (e) {
        clientErrors.push(e instanceof Error ? e.message : "Invalid label format.");
      }
    }
  }

  // The memo below reads the labels through this string, not through the array: a fresh array
  // every render would rebuild the config (and re-fire validate/plan) on every keystroke anywhere
  // on the page, and it is not something a dependency array can check.
  const labelsKey = subcorticalLabels.join(",");

  const configs: BlenderConfig[] = useMemo(() => {
    if (clientErrors.length > 0) return [];
    switch (mode) {
      case "regions":
        return buildRegionConfigs({ subjectId, simulationName, atlas, fieldName: regionField, regions });
      case "vectors":
        return [
          buildVectorConfig({
            subjectId,
            simulationName,
            exportCh1Ch2,
            exportSum,
            exportTiNormal,
            count: count ?? 10000,
            allNodes,
            seed: seed ?? 42,
            lengthScale: lengthScale ?? 1,
            vectorWidth: vectorWidth ?? 1,
            anchor: anchor === "head" ? "head" : "tail",
            color: color === "magscale" ? "magscale" : "rgb",
            bluePercentile: bluePct ?? 50,
            greenPercentile: greenPct ?? 80,
            redPercentile: redPct ?? 95,
          }),
        ];
      case "montage":
        return [
          buildMontageConfig({
            subjectId,
            simulationName,
            montageOnly,
            electrodeDiameterMm: diameter ?? 10,
            electrodeHeightMm: height ?? 6,
          }),
        ];
      case "subcortical":
        return [buildSubcorticalConfig({ subjectId, simulationName, niftiPath, labels: labelsKey ? labelsKey.split(",").map(Number) : [], cleanComponents, fieldName: subcortField })];
      case "networks":
        return [
          buildNetworkConfig({
            subjectId,
            simulationName,
            selection,
            preset: networkValue.how === "preset" ? networkValue.preset : undefined,
            overrides: networkOverrides,
            ownNetwork: ownActive ? ownNetwork : undefined,
            metric: networkMetric,
            stills: networkStills,
            turntable: networkTurntable,
            exportBlend: networkExportBlend,
            quality: networkQuality,
          }),
        ];
    }
  }, [
    clientErrors.length,
    mode,
    subjectId,
    simulationName,
    atlas,
    regionField,
    regions,
    exportCh1Ch2,
    exportSum,
    exportTiNormal,
    count,
    allNodes,
    seed,
    lengthScale,
    vectorWidth,
    anchor,
    color,
    bluePct,
    greenPct,
    redPct,
    montageOnly,
    diameter,
    height,
    niftiPath,
    labelsKey,
    cleanComponents,
    subcortField,
    selection,
    networkValue.how,
    networkValue.preset,
    networkOverrides,
    ownActive,
    ownNetwork,
    networkMetric,
    networkStills,
    networkTurntable,
    networkExportBlend,
    networkQuality,
  ]);

  // The plan and the validation speak for the first config; the regions mode submits two jobs
  // that differ only in `format`, so one plan is the honest answer for both.
  const head = configs[0] ?? null;
  const debouncedKey = useDebounced(head ? JSON.stringify(head) : "", 350);
  const validateQuery = useQuery({
    queryKey: ["validate-blender", debouncedKey],
    queryFn: () => validateBlender(JSON.parse(debouncedKey) as BlenderConfig),
    enabled: debouncedKey !== "",
  });
  const planQuery = useQuery({
    queryKey: ["plan-blender", debouncedKey, subjectId],
    queryFn: () => planBlender(JSON.parse(debouncedKey) as BlenderConfig, [subjectId]),
    enabled: debouncedKey !== "" && validateQuery.data?.ok === true,
  });
  const serverErrors = validateQuery.data?.errors.map((e) => `${e.path ? `${e.path}: ` : ""}${e.message}`) ?? [];
  const loading = head !== null && (validateQuery.isPending || planQuery.isFetching);
  const networkSetup = planQuery.data?.resolved?.network_setup as NetworkSetupRecord | undefined;
  const plannedFiles = (planQuery.data?.resolved?.planned_outputs as string[] | undefined) ?? [];
  const blendMb = planQuery.data?.resolved?.blend_size_mb as number | undefined;
  const networkRenders = networksQuery.data?.renders ?? [];

  function handleRunClick() {
    if (configs.length === 0) {
      notify.error(clientErrors[0] ?? "Complete the configuration before running.");
      return;
    }
    // The plan answers first, so the question comes before the assess job is queued.
    if (assessing === "replace") {
      setRefused(configs);
      return;
    }
    void run();
  }

  async function run(batch: BlenderConfig[] = configs, overwrite = false) {
    setSubmitting(true);
    let queued = 0;
    try {
      // A network not assessed yet is assessed first, by a job the render waits for.
      const after: string[] = [];
      if (selection && assessing && assessing !== "ready") {
        const assess = await createTractJob(buildNetworkAssessConfig(subjectId, simulationName, selection), subjectId, overwrite);
        jobs.trackJob(assess);
        after.push(assess.id);
      }
      if (ownNeedsAssess) {
        const assess = await createTractJob(buildOwnAssessConfig(subjectId, simulationName, ownNetwork), subjectId, overwrite);
        jobs.trackJob(assess);
        after.push(assess.id);
      }
      for (const config of batch) {
        jobs.trackJob(await createBlenderJob(config, [subjectId], overwrite, after));
        queued += 1;
      }
      const n = batch.length;
      notify.success(`Queued: ${n === 1 ? "1 export" : `${n} exports`} → ${outputHint(mode, subjectId, simulationName)}`);
    } catch (error) {
      // The export exists: ask, and on Replace resend only the jobs not already queued.
      if (!overwrite && isExistingOutputsConflict(error)) setRefused(batch.slice(queued));
      else notifySubmitError("Could not queue the export job.", error);
    } finally {
      setSubmitting(false);
    }
  }

  const digest = panelDigest(clientErrors, planQuery.data, loading);

  return (
    <PageLayout
      variant="run"
      rightPaneKind="run"
      paneController={scenePane}
      rightPane={
        <ExtensionRunPanel
          kind={mode === "networks" ? ["blender", "tract"] : "blender"}
          subjects={subjectId ? [subjectId] : []}
          {...jobs}
          paneControls={<PaneHeaderControls controller={scenePane} />}
          planLine={
            mode === "networks"
              ? networkPlanLine({
                  jobs: 1 + ((selection && assessing && assessing !== "ready") || ownNeedsAssess ? 1 : 0),
                  memGb: planQuery.data?.cost.mem_gb,
                  network: ownActive ? ownNetwork : undefined,
                  streamlines: ownActive ? undefined : countQuery.data,
                  blendMb,
                })
              : undefined
          }
          extraTab={mode === "networks" ? { label: `Renders ${networkRenders.filter(isPicture).length}`, content: <NetworkRenders renders={networkRenders} /> } : undefined}
          sceneFocusKey={mode === "networks" && chooserActive ? `${networkValue.how}|${networkValue.preset}|${networkValue.pairs.length}|${networkValue.includeOpposite}` : undefined}
          plan={<>
            <PlanSummary plan={planQuery.data} loading={loading}
              error={planQuery.error ? "Could not compute the plan." : undefined}
              serverErrors={serverErrors} idleMessage="Choose a subject and export type to see the plan." />
            {selection && assessing && assessing !== "ready" && (
              <p className="field-help" data-testid="ve-assess-first">
                {assessing === "replace" ? `Replaces this simulation's ${selection.name}.trx, which holds other edges. ` : ""}
                A tract job assesses this network first (about 3 min: fields along every streamline), and the render waits for it.
              </p>
            )}
            {ownNeedsAssess && (
              <p className="field-help" data-testid="ve-assess-first">
                A tract job assesses this file first (fields along every streamline), and the render waits for it.
              </p>
            )}
            {plannedFiles.length > 0 && (
              <p className="field-help" data-testid="ve-planned-files">
                Writes: {plannedFiles.map((file) => (file === "network.blend" && blendMb !== undefined ? `${file} (about ${blendMb} MB, the ${networkMetric === "direction" ? "fibre direction" : "TI_max"} scene)` : file)).join(", ")}
              </p>
            )}
            {configs.length > 1 && <p className="field-help">Cortical exports queue STL and PLY jobs; both logs stay available here.</p>}
          </>}
          scene={<ExportPreview
            mode={mode} subjectId={subjectId} simulationName={simulationName}
            simulationPath={simulationPath}
            montage={montageQuery}
            atlas={atlas} regions={regions} onRegionsChange={setRegions} onAtlasChange={setAtlas}
            montageOnly={montageOnly} diameterMm={diameter ?? 10}
            labels={subcorticalLabels} niftiPath={niftiPath}
            onLabelsChange={(labels) => { setLabelIds(labels.map(String)); setLabelsText(labels.join(",")); }}
            fieldName={mode === "subcortical" ? subcortField : regionField}
            networkValue={chooserActive ? networkValue : null}
            onNetworkChange={onNetworkChange}
          />}
        />
      }
      actionBar={
        <ActionBar
          digest={digest}
          blocked={clientErrors.length > 0}
          primary={
            <Button
              variant="primary"
              icon={<Play size={14} />}
              loading={submitting}
              onClick={handleRunClick}
              data-testid="run-button"
              title={clientErrors[0] ?? undefined}
            >
              Run export
            </Button>
          }
        />
      }
    >
      <div className="panel-page">
        <div className="panel-page-col">
          <div className="panel-page-col">
            <Card>
              <CardHeader
                title="Selection"
                actions={
                  <HelpIcon title="Visual exporter" label="About this page" text="Export STL/PLY cortical regions, vector clouds, montage visualizations and white-matter network renders." />
                }
              />
              <CardBody>
                <div className="form-grid">
                  <Field label="Subject" htmlFor="ve-subject">
                    <Select
                      id="ve-subject"
                      value={subjectId || undefined}
                      onValueChange={(v) => {
                        setSubjectId(v);
                        setSimulationName("");
                        setRegions([]);
                        setLabelIds([]);
                        setLabelsText("");
                        setNiftiPath("");
                        setOwnNetwork("");
                        setNetworkValue(FRESH_NETWORK);
                      }}
                      options={subjectOptions}
                      placeholder="Subject"
                    />
                  </Field>
                  <Field
                    label="Simulation"
                    htmlFor="ve-simulation"
                    help={mode === "subcortical" ? "Optional — without one, no field-coloured PLY is written." : undefined}
                  >
                    <Select
                      id="ve-simulation"
                      value={simulationName || undefined}
                      onValueChange={setSimulationName}
                      options={simulationOptions}
                      placeholder={subjectId ? "Simulation" : "Pick a subject first"}
                      disabled={!subjectId}
                    />
                  </Field>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Mode" />
              <CardBody>
                <SegmentedControl aria-label="Export mode" value={mode} onValueChange={setMode} options={MODE_OPTIONS} />
              </CardBody>
            </Card>

            {mode === "regions" && (
              <Card>
                <CardHeader title="Cortical regions" />
                <CardBody>
                  <div className="form-grid">
                    <Field label="Atlas" htmlFor="ve-atlas">
                      <Select
                        id="ve-atlas"
                        value={atlas}
                        onValueChange={(v) => {
                          setAtlas(v);
                          setRegions([]);
                        }}
                        options={ATLAS_OPTIONS}
                      />
                    </Field>
                    <Field label="Field" htmlFor="ve-region-field" help="Scalar field mapped onto each region mesh.">
                      <TextInput id="ve-region-field" value={regionField} onChange={(e) => setRegionField(e.target.value)} placeholder="TI_max" />
                    </Field>
                  </div>
                  <Field label="Regions" help="Nothing chosen exports the whole grey-matter surface only — the Qt widget's own rule.">
                    <SelectionPicker
                      items={regionItems}
                      value={regions}
                      onChange={setRegions}
                      label="Cortical regions"
                      title={`${atlas} — choose regions`}
                      headers={{ label: "Region", detail: "Hemisphere" }}
                      filterPlaceholder="Filter regions…"
                      idPrefix="ve-regions"
                      placeholder="Whole grey matter only"
                      loading={regionsQuery.isPending && !!subjectId}
                      disabled={!subjectId}
                      triggerTestId="ve-regions-trigger"
                    />
                  </Field>
                </CardBody>
              </Card>
            )}

            {mode === "vectors" && (
              <>
                <Card>
                  <CardHeader title="Vector customization" />
                  <CardBody>
                    <div className="form-grid">
                      <Field label="Vector length" htmlFor="ve-length">
                        <NumberInput id="ve-length" value={lengthScale} onValueChange={setLengthScale} min={0} max={1000} step={0.1} />
                      </Field>
                      <Field label="Vector width" htmlFor="ve-width">
                        <NumberInput id="ve-width" value={vectorWidth} onValueChange={setVectorWidth} min={0.001} max={100} step={0.1} />
                      </Field>
                      <Field label="Anchor" htmlFor="ve-anchor" help="Which end of the arrow touches the surface.">
                        <Select id="ve-anchor" value={anchor} onValueChange={setAnchor} options={ANCHOR_OPTIONS} />
                      </Field>
                      <Field label="Color scale" htmlFor="ve-color">
                        <Select id="ve-color" value={color} onValueChange={setColor} options={COLOR_OPTIONS} />
                      </Field>
                    </div>
                    {color === "magscale" && (
                      <div className="form-grid">
                        <Field label="Blue percentile" htmlFor="ve-blue">
                          <NumberInput id="ve-blue" value={bluePct} onValueChange={setBluePct} min={0} max={100} step={1} unit="%" />
                        </Field>
                        <Field label="Green percentile" htmlFor="ve-green">
                          <NumberInput id="ve-green" value={greenPct} onValueChange={setGreenPct} min={0} max={100} step={1} unit="%" />
                        </Field>
                        <Field label="Red percentile" htmlFor="ve-red">
                          <NumberInput id="ve-red" value={redPct} onValueChange={setRedPct} min={0} max={100} step={1} unit="%" />
                        </Field>
                      </div>
                    )}
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Processing options" />
                  <CardBody>
                    <div className="form-grid">
                      <Field label="Seed" htmlFor="ve-seed">
                        <NumberInput id="ve-seed" value={seed} onValueChange={setSeed} min={0} max={1000000} step={1} />
                      </Field>
                      <Field label="Sample count" htmlFor="ve-count" help={allNodes ? "Ignored while every node is exported." : undefined}>
                        <NumberInput id="ve-count" value={count} onValueChange={setCount} min={1} max={2000000} step={1000} disabled={allNodes} />
                      </Field>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                      <Checkbox checked={allNodes} onCheckedChange={setAllNodes} label="Use maximum (all nodes)" />
                      <Checkbox checked={exportCh1Ch2} onCheckedChange={setExportCh1Ch2} label="Export CH1 and CH2 vectors" />
                      <Checkbox checked={exportSum} onCheckedChange={setExportSum} label="Export TI_sum vector" />
                      <Checkbox checked={exportTiNormal} onCheckedChange={setExportTiNormal} label="Export TI_normal vector" />
                    </div>
                  </CardBody>
                </Card>
              </>
            )}

            {mode === "montage" && (
              <Card>
                <CardHeader title="Montage visualizer" />
                <CardBody>
                  <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                    <Checkbox
                      checked={montageOnly}
                      onCheckedChange={setMontageOnly}
                      label="Show only montage electrodes — otherwise the whole net is placed"
                    />
                    <div className="form-grid">
                      <Field label="Electrode diameter" htmlFor="ve-diameter">
                        <NumberInput id="ve-diameter" value={diameter} onValueChange={setDiameter} min={1} max={100} step={0.5} unit="mm" />
                      </Field>
                      <Field label="Electrode height" htmlFor="ve-height">
                        <NumberInput id="ve-height" value={height} onValueChange={setHeight} min={1} max={50} step={0.5} unit="mm" />
                      </Field>
                    </div>
                    <p className="field-help">
                      Writes a publication-ready Blender scene (scalp, grey matter, and the simulation&rsquo;s own electrodes) under{" "}
                      <code>visual_exports/sub-{subjectId || "…"}/montage_publication/</code>.
                    </p>
                  </div>
                </CardBody>
              </Card>
            )}

            {mode === "subcortical" && (
              <Card>
                <CardHeader title="Sub-cortical" />
                <CardBody>
                  <Field
                    label="NIfTI file"
                    htmlFor="ve-nifti"
                    help="Leave empty for the subject's own segmentation/labeling.nii.gz."
                  >
                    <TextInput id="ve-nifti" value={niftiPath} onChange={(e) => setNiftiPath(e.target.value)} placeholder="Auto — m2m segmentation/labeling.nii.gz" />
                  </Field>
                  <div className="form-grid">
                    {labelsBrowsable ? (
                      <Field label="Labels to extract" help="Nothing chosen meshes the whole volume.">
                        <SelectionPicker
                          items={labelItems}
                          value={labelIds}
                          onChange={setLabelIds}
                          label="Labels"
                          title="Choose labels to extract"
                          description="Every integer label present in this volume, named from its colour table."
                          headers={{ label: "Structure", detail: "Label · size" }}
                          filterPlaceholder="Filter by name or id…"
                          idPrefix="ve-labels"
                          placeholder="Whole volume"
                          triggerTestId="ve-labels-trigger"
                        />
                      </Field>
                    ) : (
                      <Field
                        label="Labels to extract"
                        htmlFor="ve-labels"
                        help={
                          labelsQuery.isPending && subjectId
                            ? "Reading the labels in this volume…"
                            : "Comma-separated, e.g. 10,49. Empty meshes the whole volume."
                        }
                      >
                        <TextInput id="ve-labels" value={labelsText} onChange={(e) => setLabelsText(e.target.value)} placeholder="10,49" />
                      </Field>
                    )}
                    <Field label="Field (for PLY)" htmlFor="ve-subcort-field">
                      <TextInput id="ve-subcort-field" value={subcortField} onChange={(e) => setSubcortField(e.target.value)} placeholder="TI_max" />
                    </Field>
                  </div>
                  <Checkbox checked={cleanComponents} onCheckedChange={setCleanComponents} label="Remove small disconnected components" />
                  <p className="field-help">
                    STL and MSH geometry are always written; a field-coloured PLY is added when a simulation is chosen and its subject-space field volume
                    exists.
                  </p>
                </CardBody>
              </Card>
            )}
            {mode === "networks" && (
              <Card>
                <CardHeader title="Networks" />
                <CardBody>
                  {!simulationName ? (
                    <p className="field-help">Choose a simulation to render its networks.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                          <NetworkChooser
                            value={networkValue}
                            onChange={onNetworkChange}
                            subject={subjectId}
                            simulation={simulationName}
                            defaultHow="preset"
                            strongestEmpty={<AssessNetworks subjectId={subjectId} simulationName={simulationName} onQueued={(job) => { jobs.trackJob(job); jobs.setPinnedJobId(job.id); }} />}
                            extra={{
                              label: "Your own file",
                              active: networkOwnFile,
                              onSelect: () => setNetworkOwnFile(!networkOwnFile),
                              content: <OwnNetworkPicker subject={subjectId} value={ownNetwork} onChange={setOwnNetwork} />,
                            }}
                          />
                          <Field label="Colour by" htmlFor="ve-network-metric">
                            <Select
                              id="ve-network-metric"
                              value={networkMetric}
                              onValueChange={(v) => setNetworkMetric(v === "ti_max" ? "ti_max" : "direction")}
                              options={NETWORK_METRIC_OPTIONS}
                            />
                          </Field>
                          <Checkbox checked={networkStills} onCheckedChange={setNetworkStills} label="Figure: lateral, top, front and back" />
                          <Checkbox checked={networkTurntable} onCheckedChange={setNetworkTurntable} label="Turntable video" />
                          <Checkbox checked={networkExportBlend} onCheckedChange={setNetworkExportBlend} label="Export .blend" />
                          <NetworkAdvanced subject={subjectId} overrides={networkOverrides} onChange={setNetworkOverrides} setup={networkSetup} />
                      <Field label="Quality" htmlFor="ve-network-quality" help="Fast preview samples and sizes less, to check a choice before a long render.">
                        <Select
                          id="ve-network-quality"
                          value={networkQuality}
                          onValueChange={(v) => setNetworkQuality(v === "final" ? "final" : "preview")}
                          options={NETWORK_QUALITY_OPTIONS}
                        />
                      </Field>
                    </div>
                  )}
                </CardBody>
              </Card>
            )}
          </div>


        </div>
      </div>

      <ExistingOutputsDialog
        open={refused !== null}
        onOpenChange={(open) => !open && setRefused(null)}
        existing={1}
        total={1}
        noun="export"
        busy={submitting}
        onDecide={(decision) => {
          const batch = refused;
          setRefused(null);
          if (decision === "replace" && batch) void run(batch, true);
        }}
      />
    </PageLayout>
  );
}

const page: PageDef = {
  id: "panel-visual-exporter",
  title: "3D visual exporter",
  purpose: "Export STL/PLY cortical regions, vector clouds, montage visualizations and white-matter network renders.",
  navGroup: "panels",
  order: 130,
  icon: Boxes,
  Component: VisualExporterPanel,
  enabled: isPanelEnabled("visual-exporter"),
};

export default page;
