/**
 * What the render of a chosen network will do (`tit.blender.network_setup`): the Plan's statement of
 * it, and the Advanced fields that replace any one value. An absent key is automatic.
 */
import type { ReactNode } from "react";
import { useTractManifest } from "../../_shared/roi/tract";
import { Field } from "../../../ui/Field";
import { NumberInput } from "../../../ui/NumberInput";
import { Select } from "../../../ui/Select";
import { SelectionPicker } from "../../../ui/SelectionList";
import { removedSentence, type TractPreset } from "../../_shared/roi/networkChoice";

const AUTO = "auto";

export interface NetworkSetupRecord {
  values: {
    highlight_regions: string[];
    lateral_side: number;
    max_streamlines: number;
    tube_radius_mm: number;
    vmax_v_per_m: number | null;
    iso_shell_percentile: number | null;
  };
  reasons: Record<string, string>;
  overridden: string[];
  n_streamlines: number;
  n_drawn: number;
  opposite_removed?: {
    n_kept: number;
    n_with_opposite: number;
    n_removed: number;
    right_thalamus_to_left_cortex: number;
    left_thalamus_to_right_cortex: number;
  } | null;
}

const count = (n: number) => n.toLocaleString("en-US");

/** `8 cingulate regions` when a word runs through them all, else `8 regions`; few are just named. */
export function summarizeRegions(regions: readonly string[]): string {
  if (regions.length <= 3) return regions.join(", ");
  const bare = regions.map((r) => r.replace(/^(lh\.|rh\.|Left-|Right-)/, "").toLowerCase());
  const first = bare[0]!;
  for (let size = first.length; size >= 5; size -= 1) {
    for (let at = 0; at + size <= first.length; at += 1) {
      const word = first.slice(at, at + size);
      if (bare.every((name) => name.includes(word))) return `${regions.length} ${word} regions`;
    }
  }
  return `${regions.length} regions`;
}

/** The setup in a few words, for the collapsed section's own title. */
export function setupSummary(setup: NetworkSetupRecord): string {
  const v = setup.values;
  const drawn = setup.n_drawn < setup.n_streamlines ? `${count(setup.n_drawn)} of ${count(setup.n_streamlines)} drawn` : null;
  return [v.lateral_side < 0 ? "left side" : "right side", drawn, v.iso_shell_percentile === null ? "no shell" : `shell p${v.iso_shell_percentile}`].filter(Boolean).join(" · ");
}

function rows(setup: NetworkSetupRecord): [string, string, ReactNode][] {
  const v = setup.values;
  const drawn = setup.n_drawn < setup.n_streamlines ? `${count(setup.n_drawn)} of ${count(setup.n_streamlines)}, evenly sampled` : `all ${count(setup.n_streamlines)}`;
  return [
    [
      "highlight_regions",
      "Lit regions",
      v.highlight_regions.length > 3 ? (
        <details>
          <summary>{summarizeRegions(v.highlight_regions)}</summary>
          {v.highlight_regions.join(", ")}
        </details>
      ) : (
        summarizeRegions(v.highlight_regions)
      ),
    ],
    ["lateral_side", "Lateral panel", v.lateral_side < 0 ? "left" : "right"],
    ["max_streamlines", "Streamlines drawn", drawn],
    ["tube_radius_mm", "Tube radius", `${v.tube_radius_mm.toFixed(2)} mm`],
    ["vmax_v_per_m", "Top of the colours", v.vmax_v_per_m === null ? "99.5th percentile, at render" : `${v.vmax_v_per_m} V/m`],
    ["iso_shell_percentile", "TI_max shell", v.iso_shell_percentile === null ? "none" : `brain p${v.iso_shell_percentile}`],
  ];
}

/** Every value the render will use, why, and whether the user set it, in the form that overrides it. */
export function NetworkSetupPlan({ setup }: { setup: NetworkSetupRecord }) {
  const removed = setup.opposite_removed;
  return (
    <div data-testid="network-setup-plan">
      {removed && (
        <p className="field-help" data-testid="network-setup-removed">
          {removedSentence({
            n_streamlines: removed.n_kept,
            n_opposite: removed.n_removed,
            right_thalamus_to_left_cortex: removed.right_thalamus_to_left_cortex,
            left_thalamus_to_right_cortex: removed.left_thalamus_to_right_cortex,
          } as TractPreset)}
        </p>
      )}
      <dl className="network-setup-list">
        {rows(setup).map(([key, label, value]) => (
          <div key={key} data-setup={key} title={setup.reasons[key]}>
            <dt>{label}</dt>
            <dd>
              {value}
              {setup.overridden.includes(key) ? " (set by you)" : ""}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function withKey(overrides: Record<string, unknown>, key: string, value: unknown): Record<string, unknown> {
  const { [key]: _gone, ...rest } = overrides;
  void _gone;
  return value === undefined ? rest : { ...rest, [key]: value };
}

/** Every automatic value's override. Leaving a field empty or on Automatic leaves it automatic. */
export function NetworkAdvanced({ subject, overrides, onChange, setup, disabled }: {
  subject: string;
  overrides: Record<string, unknown>;
  onChange: (overrides: Record<string, unknown>) => void;
  setup?: NetworkSetupRecord;
  disabled?: boolean;
}) {
  const manifest = useTractManifest(subject);
  const regionItems = (manifest.data?.regions ?? []).map((r) => ({ id: r.name, label: r.name, detail: r.cortical ? "cortical" : "subcortical", search: r.name }));
  const set = (key: string, value: unknown) => onChange(withKey(overrides, key, value));
  const number = (key: string, value: number | undefined) => set(key, value === undefined || !(value > 0) ? undefined : value);
  const shell = "iso_shell_percentile" in overrides ? (overrides.iso_shell_percentile === null ? "off" : "set") : AUTO;
  return (
    <details data-testid="network-advanced">
      <summary className="card-title">Setup{setup ? <span className="field-help" data-testid="network-setup-summary"> · {setupSummary(setup)}</span> : null}</summary>
      {setup && <NetworkSetupPlan setup={setup} />}
      <div className="form-grid" style={{ marginTop: "var(--space-2)" }}>
        <Field label="Lateral panel" htmlFor="ve-setup-side">
          <Select id="ve-setup-side" disabled={disabled} value={overrides.lateral_side === undefined ? AUTO : String(overrides.lateral_side)} onValueChange={(v) => set("lateral_side", v === AUTO ? undefined : Number(v))}
            options={[{ value: AUTO, label: "Automatic" }, { value: "-1", label: "Left" }, { value: "1", label: "Right" }]} />
        </Field>
        <Field label="Most streamlines drawn" help="An even sample above this.">
          <NumberInput value={overrides.max_streamlines as number | undefined} min={1} step={500} disabled={disabled} placeholder="Automatic" onValueChange={(v) => number("max_streamlines", v)} />
        </Field>
        <Field label="Tube radius" help="mm">
          <NumberInput value={overrides.tube_radius_mm as number | undefined} min={0.01} step={0.01} disabled={disabled} placeholder="Automatic" onValueChange={(v) => number("tube_radius_mm", v)} />
        </Field>
        <Field label="Top of the colours" help="V/m. Fix it to compare renders on one scale.">
          <NumberInput value={overrides.vmax_v_per_m as number | undefined} min={0.001} step={0.05} disabled={disabled} placeholder="Automatic" onValueChange={(v) => number("vmax_v_per_m", v)} />
        </Field>
        <Field label="TI_max shell" htmlFor="ve-setup-shell">
          <Select id="ve-setup-shell" disabled={disabled} value={shell} onValueChange={(v) => set("iso_shell_percentile", v === AUTO ? undefined : v === "off" ? null : 95)}
            options={[{ value: AUTO, label: "Automatic" }, { value: "off", label: "None" }, { value: "set", label: "At a percentile" }]} />
        </Field>
        {shell === "set" && (
          <Field label="Shell percentile" help="Volume-weighted, over the brain.">
            <NumberInput value={overrides.iso_shell_percentile as number} min={1} max={99.9} step={1} disabled={disabled} onValueChange={(v) => set("iso_shell_percentile", v ?? 95)} />
          </Field>
        )}
      </div>
      <Field label="Lit regions" help="Empty leaves it automatic.">
        <SelectionPicker
          items={regionItems}
          value={(overrides.highlight_regions as string[]) ?? []}
          onChange={(regions) => set("highlight_regions", regions.length ? regions : undefined)}
          label="Regions"
          title="Choose the regions to light"
          headers={{ label: "Region", detail: "Kind" }}
          filterPlaceholder="Filter regions…"
          idPrefix="ve-setup-lit"
          placeholder="Automatic"
          disabled={disabled}
        />
      </Field>
    </details>
  );
}
