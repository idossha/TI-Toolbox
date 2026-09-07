/**
 * 3D Visual Exporter — the v3 migration of `tit/gui/extensions/visual_exporter.py` (1431 lines).
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
 * byte-identical to 2.5.0's. See `PARITY.md`.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Boxes, Play, Info } from "lucide-react";
import type { PageDef } from "../../../app/registry";
import { usePageSession } from "../../../app/pageSession";
import { getSubjects } from "../../../api/client";
import { Card, CardBody, CardHeader, PageLayout } from "../../../ui/Layout";
import { usePageScrollMemory } from "../../_shared/session/usePageScrollMemory";
import { Field, TextInput } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { NumberInput } from "../../../ui/NumberInput";
import { Checkbox } from "../../../ui/Toggle";
import { SegmentedControl } from "../../../ui/SegmentedControl";
import { SelectionPicker, type SelectionItem } from "../../../ui/SelectionList";
import { Button, IconButton } from "../../../ui/Button";
import { Tooltip } from "../../../ui/Overlay";
import { notify } from "../../../ui/Toast";
import { ActionBar } from "../../../ui/Chrome";
import { isPanelEnabled, panelDigest } from "../_shared";
import "../panels.css";
import { PlanSummary } from "../PlanSummary";
import { createBlenderJob, getAtlasRegions, getNiftiLabels, getSimulationsFor, planBlender, validateBlender, type BlenderConfig } from "./api";
import {
  buildMontageConfig,
  buildRegionConfigs,
  buildSubcorticalConfig,
  buildVectorConfig,
  outputHint,
  parseLabels,
  type Mode,
} from "./config";

const MODE_OPTIONS: { value: Mode; label: string }[] = [
  { value: "regions", label: "Cortical regions" },
  { value: "vectors", label: "Field vectors" },
  { value: "montage", label: "Montage visualizer" },
  { value: "subcortical", label: "Sub-cortical" },
];

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

  const [submitting, setSubmitting] = useState(false);

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

  function handleRunClick() {
    if (configs.length === 0) {
      notify.error(clientErrors[0] ?? "Complete the configuration before running.");
      return;
    }
    void run();
  }

  async function run() {
    setSubmitting(true);
    try {
      for (const config of configs) await createBlenderJob(config, [subjectId]);
      const n = configs.length;
      notify.success(`Queued: ${n === 1 ? "1 export" : `${n} exports`} → ${outputHint(mode, subjectId, simulationName)}`);
    } catch {
      notify.error("Could not queue the export job.");
    } finally {
      setSubmitting(false);
    }
  }

  const digest = panelDigest(clientErrors, planQuery.data, loading);

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
        <div className="panel-page-split">
          <div className="panel-page-col">
            <Card>
              <CardHeader
                title="Selection"
                actions={
                  <Tooltip label="Export STL/PLY cortical regions, vector clouds, and montage visualizations for 3D rendering.">
                    <IconButton icon={<Info size={13} />} aria-label="About this page" variant="ghost" size="sm" />
                  </Tooltip>
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
          </div>

          <div className="panel-page-col">
            <Card>
              <CardHeader title="Plan" />
              <CardBody>
                <PlanSummary
                  plan={planQuery.data}
                  loading={loading}
                  error={planQuery.error ? "Could not compute the plan." : undefined}
                  serverErrors={serverErrors}
                  idleMessage="Choose a subject and a mode above to see the plan."
                />
                {configs.length > 1 && (
                  <p className="field-help" style={{ marginTop: "var(--space-2)" }}>
                    Cortical regions run twice — once for STL, once for PLY — exactly as the 2.5.0 extension did.
                  </p>
                )}
              </CardBody>
            </Card>
          </div>
        </div>
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "panel-visual-exporter",
  title: "3D visual exporter",
  purpose: "Export STL/PLY cortical regions, vector clouds, and montage visualizations for 3D rendering.",
  navGroup: "panels",
  order: 130,
  icon: Boxes,
  Component: VisualExporterPanel,
  enabled: isPanelEnabled("visual-exporter"),
};

export default page;
