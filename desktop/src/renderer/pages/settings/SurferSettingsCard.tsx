import { QsiPrepDialog } from "../preprocess/QsiPrepDialog";
import { QsiReconDialog } from "../preprocess/QsiReconDialog";
import { defaultQsiPrepConfig, defaultQsiReconConfig, qsiPrepPreferences, qsiReconPreferences } from "../preprocess/qsi";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../ui/Button";
import { InlineError, Skeleton } from "../../ui/Feedback";
import { Field } from "../../ui/Field";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Select } from "../../ui/Select";
import { Checkbox } from "../../ui/Toggle";
import { NumberInput } from "../../ui/NumberInput";
import { Dialog } from "../../ui/Overlay";
import { NATIVE_FASTSURFER_STATUS_KEY, useNativeFastSurferStatus } from "../preprocess/NativeFastSurfer";
import { getSurferSettings, putSurferSettings, type SurferPreferences } from "./api";

export function AppleGpuSettings() {
  const status = useNativeFastSurferStatus();
  const client = useQueryClient();
  const [explaining, setExplaining] = useState(false);
  const change = useMutation({
    mutationFn: (enable: boolean) => enable ? window.tit!.fastsurfer!.enable() : window.tit!.fastsurfer!.disable(),
    onSuccess: (next) => client.setQueryData(NATIVE_FASTSURFER_STATUS_KEY, next),
  });
  const current = status.data;
  const canEnable = Boolean(window.tit?.fastsurfer && current?.supported);
  const busy = change.isPending || current?.installing;
  const error = change.error?.message || current?.error;
  return <div>
    <Field label="Apple GPU" layout="stacked">
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <Button size="sm" disabled={busy} onClick={() => current?.preferenceEnabled ? change.mutate(false) : setExplaining(true)}>
          {busy ? "Updating Apple GPU…" : current?.preferenceEnabled ? "Disable Apple GPU" : "Enable Apple GPU"}
        </Button>
        <span className="field-help" title="FastSurfer can use Apple Silicon GPU acceleration when enabled.">FastSurfer acceleration on Apple Silicon</span>
      </div>
    </Field>
    {!canEnable && <p className="field-help">NVIDIA acceleration is automatic when available in Docker. To enable Apple GPU support, open the desktop app on your Apple Silicon Mac.</p>}
    {error && <InlineError message={error} />}
    <Dialog open={explaining} onOpenChange={setExplaining} title="Enable Apple GPU"
      description="Run FastSurfer on your Mac’s GPU for faster segmentation."
      footer={<><Button onClick={() => setExplaining(false)}>Cancel</Button><Button variant="primary" disabled={!canEnable} onClick={() => { setExplaining(false); change.mutate(true); }}>Enable Apple GPU</Button></>}>
      <svg viewBox="0 0 440 88" role="img" aria-label="TI-Toolbox sends a job to the Mac GPU and saves results in the open project" style={{ width: "100%", height: 88, color: "var(--ink-2)" }}>
        <g fill="var(--surface-2)" stroke="var(--line)"><rect x="2" y="12" width="124" height="60" rx="8"/><rect x="158" y="12" width="124" height="60" rx="8"/><rect x="314" y="12" width="124" height="60" rx="8"/></g>
        <g fill="currentColor" textAnchor="middle" fontSize="13"><text x="64" y="38">TI-Toolbox</text><text x="64" y="56">Docker job</text><text x="220" y="46">Mac GPU</text><text x="376" y="38">Open project</text><text x="376" y="56">Results</text><text x="142" y="46">→</text><text x="298" y="46">→</text></g>
      </svg>
      {!canEnable && <p>Apple GPU permission must be granted in the TI-Toolbox desktop app.</p>}
      <p>TI-Toolbox downloads FastSurfer and its dependencies into your user directory without administrator access. Computation runs in a sandbox limited to the open project and its required runtime files, with no network access.</p>
      {current?.directory && <p className="field-help" style={{ overflowWrap: "anywhere" }}>Installation folder: {current.directory}</p>}
      <p>This preference applies across your projects on this Mac. You can turn it off here at any time.</p>
      <p>FastSurfer is third-party scientific software developed by Deep-MI. TI-Toolbox installs source from a pinned official FastSurfer release and verifies download checksums. Use is subject to the upstream license. TI-Toolbox provides no warranty for FastSurfer or its results and accepts no responsibility for their use; you are responsible for validating outputs for your research.</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <a href="https://idossha.github.io/TI-Toolbox/wiki/fastsurfer/#enable-apple-gpu" target="_blank" rel="noreferrer">Setup guide ↗</a>
        <a href="https://idossha.github.io/TI-Toolbox/wiki/fastsurfer/#permissions" target="_blank" rel="noreferrer">Permissions guide ↗</a>
        <a href="https://github.com/Deep-MI/FastSurfer/releases" target="_blank" rel="noreferrer">Official FastSurfer releases ↗</a>
      </div>
    </Dialog>
  </div>;
}

export function SurferSettingsCard() {
  const client = useQueryClient();
  const [qsiOpen, setQsiOpen] = useState<"qsiprep" | "qsirecon" | null>(null);
  const settings = useQuery({ queryKey: ["surfer-settings"], queryFn: getSurferSettings });
  const [draft, setDraft] = useState<SurferPreferences | null>(null);
  const save = useMutation({ mutationFn: putSurferSettings, onSuccess: (next) => { client.setQueryData(["surfer-settings"], next); setDraft(null); } });
  const values = draft ?? settings.data;
  const patch = (change: Partial<SurferPreferences>) => {
    if (!values) return;
    const next: SurferPreferences = { freesurfer_recon_all: values.freesurfer_recon_all ?? true, freesurfer_subregions: values.freesurfer_subregions ?? ["thalamus", "hippo-amygdala"] };
    for (const key of PREFERENCE_KEYS) Object.assign(next, { [key]: values[key] });
    setDraft({ ...next, ...change });
  };
  const threads = (key: ThreadKey, label: string) => values && <Field label={label} htmlFor={key}>
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
      <NumberInput id={key} aria-label={label} min={1} max={settings.data?.available_threads ?? 4096} step={1}
        value={values[key] ?? undefined} placeholder={`Auto (${settings.data?.default_threads ?? "…"})`}
        onValueChange={(value) => patch({ [key]: value ?? null })} />
      <span className="field-help">of {settings.data?.available_threads ?? "…"} available threads</span>
    </div>
  </Field>;
  return <section className="preprocessing-preferences" aria-label="Pre-processing preferences" style={{ display: "grid", gap: "var(--space-4)" }}>
    <p className="field-help">Your defaults across projects. Automatic thread allocation uses all available CPUs except one for the host.</p>
    {settings.isPending && <Skeleton height={64} />}
    <Card><CardHeader title="FastSurfer" actions={<div className="preprocessing-doc-links"><a className="field-help" href="https://idossha.github.io/TI-Toolbox/wiki/fastsurfer/" target="_blank" rel="noreferrer">TI-Toolbox docs ↗</a> <a className="field-help" href="https://deep-mi.org/FastSurfer/stable/scripts/RUN_FASTSURFER.html" target="_blank" rel="noreferrer">Upstream FastSurfer ↗</a></div>} /><CardBody>
      <AppleGpuSettings />
      {threads("fastsurfer_threads", "FastSurfer threads")}
    </CardBody></Card>
    <Card><CardHeader title="FreeSurfer" actions={<div className="preprocessing-doc-links"><a className="field-help" href="https://idossha.github.io/TI-Toolbox/wiki/pre-processing/" target="_blank" rel="noreferrer">TI-Toolbox docs ↗</a> <a className="field-help" href="https://surfer.nmr.mgh.harvard.edu/fswiki/recon-all" target="_blank" rel="noreferrer">Upstream FreeSurfer ↗</a></div>} /><CardBody>
      {threads("freesurfer_threads", "FreeSurfer threads")}
      {values && <div role="group" aria-label="FreeSurfer operations" style={{ display: "grid", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
        <Checkbox label="Full reconstruction (recon-all)" checked={values.freesurfer_recon_all ?? true} onCheckedChange={(value) => patch({ freesurfer_recon_all: value })} />
        {([["thalamus", "Thalamic nuclei"], ["hippo-amygdala", "Hippocampal / amygdala subregions"]] as const).map(([region, label]) =>
          <Checkbox key={region} label={label} checked={(values.freesurfer_subregions ?? ["thalamus", "hippo-amygdala"]).includes(region)}
            onCheckedChange={(checked) => { const selected = values.freesurfer_subregions ?? ["thalamus", "hippo-amygdala"]; patch({ freesurfer_subregions: checked ? [...selected, region] : selected.filter((item) => item !== region) }); }} />)}
        <p className="field-help">Subregions require a completed reconstruction, from this run or an existing result.</p>
      </div>}
    </CardBody></Card>
    <Card><CardHeader title="SimNIBS CHARM" actions={<div className="preprocessing-doc-links"><a className="field-help" href="https://idossha.github.io/TI-Toolbox/wiki/pre-processing/" target="_blank" rel="noreferrer">TI-Toolbox docs ↗</a> <a className="field-help" href="https://simnibs.github.io/simnibs/build/html/documentation/command_line/charm.html" target="_blank" rel="noreferrer">SimNIBS docs ↗</a></div>} /><CardBody>
      {threads("charm_threads", "CHARM threads")}
      {values && <details><summary>Advanced segmentation and mesh settings</summary>
        <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-3)" }}>
          <p className="field-help">Leave values at Default to use this SimNIBS installation’s settings. Changing resolution affects the resulting head model and computation time.</p>
          <Field label="Denoise anatomy"><div style={{ width: 280, maxWidth: "100%" }}><Select value={values.charm_options?.denoise == null ? "default" : String(values.charm_options.denoise)} options={[{ value: "default", label: "Default (enabled)" }, { value: "true", label: "Enabled" }, { value: "false", label: "Disabled" }]} onValueChange={(value) => patch({ charm_options: { ...values.charm_options, denoise: value === "default" ? null : value === "true" } })} /></div></Field>
          <Field label="Segmentation resolution" help="Final segmentation sampling resolution in mm. Smaller values require more computation.">
            <div style={{ width: 180, maxWidth: "100%" }}><NumberInput aria-label="CHARM segmentation resolution" min={0.5} max={2} step={0.1} unit="mm" placeholder="1.0" value={values.charm_options?.segmentation_final_resolution ?? undefined} onValueChange={(value) => patch({ charm_options: { ...values.charm_options, segmentation_final_resolution: value ?? null } })} /><span className="field-help">Default: 1.0 mm</span></div>
          </Field>
          <Field label="Scalp triangle size" help="Target scalp surface triangle size in mm. This is not the size of every volume element.">
            <div style={{ width: 180, maxWidth: "100%" }}><NumberInput aria-label="CHARM scalp triangle size" min={0.5} max={10} step={0.1} unit="mm" placeholder="2.0" value={values.charm_options?.skin_facet_size ?? undefined} onValueChange={(value) => patch({ charm_options: { ...values.charm_options, skin_facet_size: value ?? null } })} /><span className="field-help">Default: 2.0 mm</span></div>
          </Field>
        </div>
      </details>}
    </CardBody></Card>
    {(["qsiprep", "qsirecon"] as const).map((tool) => <Card key={tool}><CardHeader title={tool === "qsiprep" ? "QSIPrep" : "QSIRecon"} actions={<div className="preprocessing-doc-links"><a className="field-help" href="https://idossha.github.io/TI-Toolbox/wiki/pre-processing/" target="_blank" rel="noreferrer">TI-Toolbox docs ↗</a> <a className="field-help" href={tool === "qsiprep" ? "https://qsiprep.readthedocs.io/en/latest/usage.html" : "https://qsirecon.readthedocs.io/en/latest/builtin_workflows.html"} target="_blank" rel="noreferrer">{tool === "qsiprep" ? "QSIPrep docs" : "QSIRecon docs"} ↗</a></div>} /><CardBody>
      <div><Button size="sm" onClick={() => setQsiOpen(tool)}>Configure {tool === "qsiprep" ? "QSIPrep" : "QSIRecon"}…</Button></div>
      {threads(`${tool}_threads`, "CPU threads")}
      {threads(`${tool}_omp_threads`, "OpenMP threads")}
      {values && <Field label="Memory (GB)" htmlFor={`${tool}_memory_gb`}>
        <NumberInput id={`${tool}_memory_gb`} aria-label={`${tool} memory GB`} min={1} step={1} value={values[`${tool}_memory_gb`] ?? undefined}
          placeholder="Auto" onValueChange={(value) => patch({ [`${tool}_memory_gb`]: value ?? null })} />
      </Field>}
    </CardBody></Card>)}
    <QsiPrepDialog open={qsiOpen === "qsiprep"} onOpenChange={(open) => !open && setQsiOpen(null)} initial={{ ...defaultQsiPrepConfig(), ...values?.qsiprep_config }} onSave={(config) => save.mutate({ ...draft, qsiprep_config: qsiPrepPreferences(config) })} />
    <QsiReconDialog open={qsiOpen === "qsirecon"} onOpenChange={(open) => !open && setQsiOpen(null)} initial={{ ...defaultQsiReconConfig(), ...values?.qsi_recon_config }} onSave={(config) => save.mutate({ ...draft, qsi_recon_config: qsiReconPreferences(config) })} />
    <div><Button size="sm" disabled={!draft || save.isPending} onClick={() => draft && save.mutate(draft)}>Save pre-processing preferences</Button></div>
    {(settings.error || save.error) && <InlineError message={(settings.error || save.error)!.message} />}
  </section>;
}

type ThreadKey = "fastsurfer_threads" | "freesurfer_threads" | "charm_threads" | "qsiprep_threads" | "qsirecon_threads" | "qsiprep_omp_threads" | "qsirecon_omp_threads";
const PREFERENCE_KEYS = ["fastsurfer_threads", "freesurfer_threads", "charm_threads", "qsiprep_threads", "qsirecon_threads", "qsiprep_omp_threads", "qsirecon_omp_threads", "qsiprep_memory_gb", "qsirecon_memory_gb", "freesurfer_recon_all", "freesurfer_subregions", "qsiprep_config", "qsi_recon_config", "charm_options"] as const;
