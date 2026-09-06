import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import type { TitStackStatus } from "../../../shared/tit-bridge";
import type { PageDef } from "../../app/registry";
import { usePageSession } from "../../app/pageSession";
import { useThemeStore, type ThemeSetting } from "../../app/theme/store";
import { useExecutionPrefs, type ExistingOutputPolicy } from "../../app/executionPrefs";
import { isElectron } from "../../env";
import { Button } from "../../ui/Button";
import { Callout, DefinitionList, Skeleton } from "../../ui/Feedback";
import { Field, TextInput } from "../../ui/Field";
import { Card, CardBody, CardHeader, PageLayout } from "../../ui/Layout";
import { NumberInput } from "../../ui/NumberInput";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Checkbox, Switch } from "../../ui/Toggle";
import { notify } from "../../ui/Toast";
import { getCapabilities, getProject, getSettings, getVersion, putSettings, type Settings } from "./api";
import { readEnabledPanels, writeEnabledPanels, type PanelId } from "../panels/_shared";
import { usePageScrollMemory } from "../_shared/session/usePageScrollMemory";
import { TetravoxCard } from "./TetravoxCard";
import "./settings-page.css";

/**
 * Settings and Help are the two pages DESIGN.md §2.3 still allows a header — the orchestrator's
 * brief caps it at "a single 28px eyebrow" rather than the old 86px title-plus-purpose block
 * (`PageHeader`), so this is a smaller, page-local replacement rather than an edit to the shared
 * `PageHeader` component every other page also imports. `.page-header` is kept as the wrapping
 * class so anything scanning for it (the metrics instrument's `pageHeaderHeight`) still finds it.
 */
function PageEyebrow({ title }: { title: string }) {
  return (
    <div className="page-header" style={{ height: "var(--row-h)", alignItems: "center" }}>
      <h1 className="text-eyebrow" style={{ margin: 0 }}>
        {title}
      </h1>
    </div>
  );
}

const PANEL_INFO: { id: PanelId; label: string; description: string }[] = [
  { id: "source", label: "Source", description: "Build EEG forward solutions and map simulation fields to fsaverage." },
  { id: "cluster-permutation", label: "Cluster permutation", description: "Compare or correlate field intensities across subjects with permutation testing." },
  { id: "nifti-group-average", label: "NIfTI group averaging", description: "Compute group averages and differences of NIfTI files." },
  { id: "nilearn-visuals", label: "Nilearn visuals", description: "Create Nilearn high-resolution publication visualizations." },
  { id: "quick-notes", label: "Quick notes", description: "Keep a running project notepad." },
];

const THEME_OPTIONS: { value: ThemeSetting; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

function sameStringSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sa = [...a].sort();
  const sb = [...b].sort();
  return sa.every((v, i) => v === sb[i]);
}

/**
 * The Docker stack this app started, and the only in-app way to stop it (QA engineer finding 6).
 *
 * Before this, `stack.stop()` was reachable from the launcher alone, so once the window had
 * navigated to the container's own UI there was no way back short of `docker stop` in a terminal —
 * and quitting left the container running with nothing saying so. Electron-only by construction:
 * in browser mode there is no `window.tit`, and nothing here would have anything to stop.
 */
function DockerCard() {
  const [stopping, setStopping] = useState(false);
  const statusQuery = useQuery({
    queryKey: ["stack-status"],
    queryFn: (): Promise<TitStackStatus> => window.tit!.stack.status(),
    // The container's health flips on its own timetable (Docker polls every 10s), so read it
    // again while the page is open rather than showing whatever it said on mount.
    refetchInterval: 10_000,
  });
  const status = statusQuery.data;
  if (!status?.running) return null;

  async function handleStop() {
    setStopping(true);
    const result = await window.tit!.stack.stop();
    // A successful stop navigates this window back to the launcher, so there is no success state
    // to render here — only a failure worth reporting.
    if (!result.ok) {
      setStopping(false);
      notify.error(result.error);
    }
  }

  return (
    <Card>
      <CardHeader title="Docker" />
      <CardBody>
        <DefinitionList
          entries={[
            ["Container", status.containerName ?? "unknown"],
            ["Image", status.image ?? "unknown"],
            ["Health", status.health === "none" ? "no healthcheck" : (status.health ?? "unknown")],
          ]}
        />
        <p className="field-help" style={{ marginTop: "var(--space-3)" }}>
          Quitting leaves this container running so the next launch reconnects instantly. Stop it to free its memory and CPU; your project data and cached
          derivatives are untouched.
        </p>
        <div style={{ marginTop: "var(--space-3)" }}>
          <Button variant="destructive" loading={stopping} onClick={handleStop} data-testid="stop-stack">
            Stop Docker stack
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function SettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const projectQuery = useQuery({ queryKey: ["project"], queryFn: getProject });
  const capsQuery = useQuery({ queryKey: ["capabilities"], queryFn: getCapabilities });
  const versionQuery = useQuery({ queryKey: ["version"], queryFn: getVersion });
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  usePageScrollMemory();

  const [form, setForm] = usePageSession<Settings | null>("form", null);

  // Seed the editable form once the server settings arrive — adjusted during render (tracking
  // the previous query-data reference), not a `useEffect(() => setState(...), [data])`, matching
  // `ConductivityDialog`'s re-seed pattern (react-hooks/set-state-in-effect).
  //
  // The "previous value" baseline MUST start at a value the query can never equal on first render
  // (`undefined`, not `useState(settingsQuery.data)`). `["settings"]` is a shared query key —
  // `app/registry.ts`'s `useEnabledPages()` reads the same cache entry — so by the time this page
  // mounts, the nav rail has often already warmed the cache and `settingsQuery.data` is non-null
  // on this component's very first render. Seeding the baseline from the live data made that look
  // like "no change since last render" and `form` was never set (Telemetry/Feature panels/Advanced
  // silently never appeared — no error, no skeleton). Starting the baseline at a fixed `undefined`
  // means a first render with data already present is correctly seen as a change.
  const [prevSettingsData, setPrevSettingsData] = useState<Settings | undefined>(undefined);
  if (settingsQuery.data !== prevSettingsData) {
    setPrevSettingsData(settingsQuery.data);
    if (settingsQuery.data && form === null) setForm({ ...settingsQuery.data });
  }

  // Sync the panels localStorage mirror so a reload (e.g. after Save, or the next time the app
  // boots) reflects the project's real panel list rather than an empty first-run cache (see
  // pages/panels/_shared.ts). Pure localStorage IO, no setState — not subject to the same rule.
  useEffect(() => {
    if (!settingsQuery.data) return;
    if (!sameStringSet(readEnabledPanels(), settingsQuery.data.panels)) writeEnabledPanels(settingsQuery.data.panels);
    try {
      window.localStorage.setItem("tit-enabled-panels-synced", "1");
    } catch {
      // best-effort
    }
  }, [settingsQuery.data]);

  // Only nudge the user to reload if the nav could actually be showing something stale right now
  // (i.e. this was not simply the very first time the mirror was ever written) — a pure render-time
  // read, so it clears itself on the next render once the effect above has written the mirror.
  let syncedBefore = false;
  try {
    syncedBefore = window.localStorage.getItem("tit-enabled-panels-synced") === "1";
  } catch {
    // best-effort
  }
  const staleNotice = syncedBefore && !!settingsQuery.data && !sameStringSet(readEnabledPanels(), settingsQuery.data.panels);

  const saveMutation = useMutation({
    mutationFn: (next: Settings) => putSettings(next),
    onSuccess: (saved) => {
      const panelsChanged = !sameStringSet(readEnabledPanels(), saved.panels);
      writeEnabledPanels(saved.panels);
      // Same class of fix as pages/panels/quick-notes: without updating the query cache, `dirty`
      // (which compares `form` against `settingsQuery.data`) would immediately read stale-old
      // data again and show "Save changes" as enabled right after a successful save whenever the
      // panel list didn't change (the panels-changed path masks this by reloading the whole app).
      queryClient.setQueryData(["settings"], saved);
      setForm(saved);
      if (panelsChanged) {
        notify.success("Settings saved. Reloading to apply the panel changes…");
        window.setTimeout(() => window.location.reload(), 600);
      } else {
        notify.success("Settings saved");
      }
    },
    onError: () => notify.error("Could not save settings."),
  });

  const dirty = form !== null && settingsQuery.data !== undefined && JSON.stringify(form) !== JSON.stringify({ ...settingsQuery.data, theme });

  function patch(partial: Partial<Settings>) {
    setForm((prev) => (prev ? { ...prev, ...partial } : prev));
  }

  function togglePanel(id: PanelId, on: boolean) {
    if (!form) return;
    const next = on ? [...form.panels, id] : form.panels.filter((p) => p !== id);
    patch({ panels: next });
  }

  function handleThemeChange(value: ThemeSetting) {
    setTheme(value); // applies immediately, independent of Save (DESIGN.md §7)
  }

  function handleSave() {
    if (!form) return;
    saveMutation.mutate({ ...form, theme });
  }

  const loading = settingsQuery.isPending || projectQuery.isPending;

  // The banners (load error, stale-panels notice) sit above the columns, full width.
  const banners = (settingsQuery.error || staleNotice) && (
    <div style={{ breakInside: "avoid", marginBottom: "var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {settingsQuery.error && <Callout kind="danger">Could not load settings.</Callout>}
      {staleNotice && (
        <Callout kind="info" title="Panel list changed on the server">
          <Button variant="ghost" size="sm" onClick={() => window.location.reload()}>
            Reload now
          </Button>{" "}
          to see it reflected in the nav.
        </Callout>
      )}
    </div>
  );

  return (
    <PageLayout header={<PageEyebrow title="Settings" />}>
      {/* U1 (DESIGN.md §2): a run page's work pane has no max width. A CSS multi-column flow (not a
          grid) uses it: cards keep their own natural height and pack top-to-bottom per column, so
          a short card (Telemetry) next to a tall one (Feature panels) does not leave a grid-row's
          worth of blank space under it — a Cards' own `break-inside: avoid` keeps a card whole
          rather than split across the column break; the fixed `.settings-columns` class does that
          for the ones this file doesn't build inline (see components.css). */}
      <div className="settings-columns" style={{ columnWidth: 440, columnGap: "var(--space-4)" }}>
        {banners}

        <Card>
          <CardHeader title="Project" />
          <CardBody>
            {loading && <Skeleton height={80} />}
            {projectQuery.data && (
              <DefinitionList
                entries={[
                  ["Name", projectQuery.data.name],
                  ["Container path", projectQuery.data.container_path],
                  ...(isElectron && projectQuery.data.host_path ? ([["Host path", projectQuery.data.host_path]] as [string, string][]) : []),
                ]}
              />
            )}
            {form && (
              <div style={{ marginTop: "var(--space-3)" }}>
                <Field label="Image tag override" htmlFor="settings-image-tag" help="Pin the toolbox image to a specific tag instead of the install's default. Leave blank to use the default.">
                  <TextInput
                    id="settings-image-tag"
                    value={form.image_tag ?? ""}
                    placeholder="e.g. idossha/simnibs:v2.3.1"
                    onChange={(e) => patch({ image_tag: e.target.value.trim() === "" ? null : e.target.value })}
                  />
                </Field>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Appearance" />
          <CardBody>
            <Field label="Theme" help="Applies immediately; System follows the OS setting.">
              <SegmentedControl value={theme} onValueChange={(v) => handleThemeChange(v as ThemeSetting)} options={THEME_OPTIONS} aria-label="Theme" />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Execution" />
          <CardBody>
            {/* User-level, not per page (2026-09-06): the default answer to the existing-outputs
                question and the scheduler-enforced `Subjects in parallel` cap every run uses. */}
            <ExecutionCard />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Telemetry" />
          <CardBody>
            {form && (
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                <Switch
                  id="settings-telemetry"
                  checked={form.telemetry.enabled}
                  onCheckedChange={(enabled) => patch({ telemetry: { consented: enabled, enabled } })}
                  aria-label="Send anonymous usage data"
                />
                <label htmlFor="settings-telemetry" className="field-label" style={{ cursor: "pointer" }}>
                  Send anonymous usage data
                </label>
              </div>
            )}
            <p className="field-help" style={{ marginTop: "var(--space-2)" }}>
              No project data, file paths, or subject identifiers are ever sent — only feature usage and error counts.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Feature panels" />
          <CardBody>
            <p className="field-help" style={{ marginBottom: "var(--space-3)" }}>
              Optional tools. Enabled panels appear in the nav rail. Toggling one requires a reload to take effect.
            </p>
            {form && (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                {PANEL_INFO.map((p) => (
                  <label key={p.id} style={{ display: "flex", gap: "var(--space-3)", alignItems: "flex-start" }}>
                    <Checkbox checked={form.panels.includes(p.id)} onCheckedChange={(on) => togglePanel(p.id, on)} />
                    <span>
                      <span className="text-body" style={{ fontWeight: 500, display: "block" }}>
                        {p.label}
                      </span>
                      <span className="field-help">{p.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Advanced" />
          <CardBody>
            {form && (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                  <Switch
                    checked={form.allow_unsafe_overrides}
                    onCheckedChange={(allow_unsafe_overrides) => patch({ allow_unsafe_overrides })}
                    aria-label="Allow unsafe overrides"
                  />
                  <span className="text-body">Allow unsafe overrides</span>
                </div>
                {form.allow_unsafe_overrides && (
                  <Callout kind="warning">Lets a job be queued despite non-critical validation findings. May produce invalid or unusable results.</Callout>
                )}
              </div>
            )}

            <div style={{ marginTop: "var(--space-4)" }}>
              <span className="text-body" style={{ fontWeight: 500, display: "block", marginBottom: "var(--space-1)" }}>
                Jupyter
              </span>
              {capsQuery.data ? (
                capsQuery.data.jupyter ? (
                  <Callout kind="info">
                    Available in this environment. Start it from the container with the <code className="mono">NOTEBOOK</code> alias — there is no
                    in-app start control yet (no endpoint for it in the current server contract).
                  </Callout>
                ) : (
                  <p className="field-help">Not available in this environment.</p>
                )
              ) : (
                <Skeleton height={24} />
              )}
            </div>
          </CardBody>
        </Card>

        {/* The viewer bundle is updatable at runtime (E1-E4), so its card carries its own state
            and mutations rather than joining the Save-changes form above. */}
        <TetravoxCard />

        {isElectron && <DockerCard />}

        <Card>
          <CardHeader title="About the server" actions={<SlidersHorizontal size={14} aria-hidden style={{ color: "var(--ink-3)" }} />} />
          <CardBody>
            {versionQuery.data && (
              <DefinitionList
                entries={[
                  ["tit version", versionQuery.data.tit_version],
                  ["server API", versionQuery.data.server_api],
                  ["schema hash", versionQuery.data.schema_hash || "(none yet)"],
                  ["python", versionQuery.data.python],
                  ["simnibs", versionQuery.data.simnibs ?? "not available"],
                ]}
              />
            )}
            {capsQuery.data && (
              // Named entries, not a raw `Object.entries` dump: `Capabilities.tetravox_embed` is an
              // object, not a boolean, and blindly stringifying every key risked resurfacing the
              // retired X11/Freeview/Gmsh capability flags the server no longer even reports (D3).
              <div style={{ marginTop: "var(--space-3)" }}>
                <DefinitionList
                  entries={[
                    ["Docker socket", capsQuery.data.docker_socket ? "yes" : "no"],
                    ["Blender (bpy)", capsQuery.data.bpy ? "yes" : "no"],
                    ["FastSurfer", capsQuery.data.fastsurfer ? "yes" : "no"],
                    ["Jupyter", capsQuery.data.jupyter ? "yes" : "no"],
                    [
                      "Viewer bundle",
                      capsQuery.data.tetravox_embed.available
                        ? `v${capsQuery.data.tetravox_embed.version ?? "?"} · protocol ${capsQuery.data.tetravox_embed.protocol ?? "?"} · ${
                            capsQuery.data.tetravox_embed.source ?? "unknown source"
                          }`
                        : "none",
                    ],
                  ]}
                />
              </div>
            )}
          </CardBody>
        </Card>

        <div style={{ gridColumn: "1 / -1" }}>
          <Button variant="primary" disabled={!dirty} loading={saveMutation.isPending} onClick={handleSave}>
            Save changes
          </Button>
        </div>
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "settings",
  title: "Settings",
  purpose: "Project, appearance, telemetry, and optional panels for this install.",
  navGroup: "system",
  order: 90,
  icon: SlidersHorizontal,
  shortcut: ",",
  Component: SettingsPage,
  enabled: true,
};

export default page;

function ExecutionCard() {
  const existingOutputs = useExecutionPrefs((s) => s.existingOutputs);
  const parallelSubjects = useExecutionPrefs((s) => s.parallelSubjects);
  const setExecutionPrefs = useExecutionPrefs((s) => s.setExecutionPrefs);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <Field label="Existing outputs" help="What a run does when a subject already has this output. You are still asked before a run that would touch existing outputs.">
        <SegmentedControl
          value={existingOutputs}
          onValueChange={(v) => setExecutionPrefs({ existingOutputs: v as ExistingOutputPolicy })}
          options={[
            { value: "skip", label: "Skip existing outputs" },
            { value: "replace", label: "Replace and rerun" },
          ]}
          aria-label="Existing outputs"
        />
      </Field>
      <Field label="Subjects in parallel" help="How many subjects' jobs run at once on every run page; 1 runs them one after another. The server's scheduler enforces this, not the app.">
        <NumberInput
          value={parallelSubjects}
          onValueChange={(v) => setExecutionPrefs({ parallelSubjects: v ?? 1 })}
          min={1}
          step={1}
          aria-label="Subjects in parallel"
          data-testid="subjects-in-parallel"
          style={{ width: 96 }}
        />
      </Field>
    </div>
  );
}
