import { useState } from "react";
import { Button } from "../../ui/Button";
import { HelpIcon } from "../../ui/HelpPopover";
import { Field } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Checkbox } from "../../ui/Toggle";
import { ConductivityDialog, type CustomConductivities } from "./ConductivityDialog";
import { CONDUCTIVITY_OPTIONS, OUTPUT_FIELDS, type JobSettings } from "./types";

/** Shared per-job simulation controls, used by the Simulator and pipeline inspector. */
export function SimulationSettings({ value: draft, onChange: setDraft }: { value: JobSettings; onChange: (value: JobSettings) => void }) {
  const [tissueOpen, setTissueOpen] = useState(false);
  const invalid = draft.outputFields.length === 0;
  return <>
        <div className="job-settings-form" data-testid="job-settings-form">
          <section>
            <h4>Electrodes</h4>
            <div className="field-row-inline">
              <Field label="Shape">
                <SegmentedControl
                  value={draft.electrodeShape}
                  onValueChange={(v) => setDraft({ ...draft, electrodeShape: v as "ellipse" | "rect" })}
                  options={[
                    { value: "ellipse", label: "Ellipse" },
                    { value: "rect", label: "Rectangle" },
                  ]}
                  aria-label="Electrode shape"
                />
              </Field>
              <Field label="Dimensions">
                <div style={{ display: "flex", gap: "var(--space-2)" }}>
                  <NumberInput
                    value={draft.dimensions[0]}
                    onValueChange={(v) => setDraft({ ...draft, dimensions: [v ?? 8, draft.dimensions[1]] })}
                    unit="w"
                    step={0.5}
                    min={0}
                    aria-label="Electrode width"
                  />
                  <NumberInput
                    value={draft.dimensions[1]}
                    onValueChange={(v) => setDraft({ ...draft, dimensions: [draft.dimensions[0], v ?? 8] })}
                    unit="h"
                    step={0.5}
                    min={0}
                    aria-label="Electrode height"
                  />
                </div>
              </Field>
              <Field label="Gel thickness" className="sim-gel-field">
                <NumberInput
                  value={draft.gelThickness}
                  onValueChange={(v) => setDraft({ ...draft, gelThickness: v ?? 4 })}
                  step={0.5}
                  min={0}
                  unit="mm"
                  aria-label="Gel thickness"
                />
              </Field>
            </div>
          </section>

          <section>
            <h4>Conductivity</h4>
            <div className="field-row-inline">
              <Field label="Model">
                <Select
                  value={draft.conductivity}
                  onValueChange={(v) => setDraft({ ...draft, conductivity: v })}
                  options={CONDUCTIVITY_OPTIONS}
                  aria-label="Conductivity model"
                />
              </Field>
              {draft.conductivity !== "scalar" && <>
                <Field label="Max ratio" help="Maximum eigenvalue ratio for conductivity tensors.">
                  <NumberInput
                    value={draft.anisoMaxratio ?? 10}
                    onValueChange={(v) => setDraft({ ...draft, anisoMaxratio: v ?? 10 })}
                    min={1}
                    step={0.5}
                    aria-label="Anisotropy max ratio"
                  />
                </Field>
                <Field label="Max conductivity" help="Maximum conductivity for anisotropic tensors.">
                  <NumberInput
                    value={draft.anisoMaxcond ?? 2}
                    onValueChange={(v) => setDraft({ ...draft, anisoMaxcond: v ?? 2 })}
                    min={0.1}
                    step={0.1}
                    unit="S/m"
                    aria-label="Anisotropy max conductivity"
                  />
                </Field>
              </>}
              <Field label="Tissue values" help="Overrides SimNIBS's per-tissue defaults for this job only.">
                <Button variant="secondary" onClick={() => setTissueOpen(true)}>
                  Edit values…
                </Button>
              </Field>
            </div>
          </section>

          <section>
            <h4>Output fields</h4>
            <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
              {OUTPUT_FIELDS.map((f) => (
                <label key={f.name} title={f.description} className="checkbox-label-row">
                  <Checkbox
                    checked={draft.outputFields.includes(f.name)}
                    onCheckedChange={(checked) =>
                      setDraft({
                        ...draft,
                        outputFields: checked ? [...draft.outputFields, f.name] : draft.outputFields.filter((n) => n !== f.name),
                      })
                    }
                  />
                  {f.name}
                </label>
              ))}
            </div>
            {invalid && <span className="field-error">Select at least one output field.</span>}
          </section>
          <section>
            <h4>Surface mapping</h4>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
              <label className="checkbox-label-row">
                <Checkbox checked={draft.mapToFsavg ?? false} onCheckedChange={(checked) => setDraft({ ...draft, mapToFsavg: checked })} />
                Map fields to fsaverage
              </label>
              <HelpIcon variant="plain" title="Surface mapping" text="Project this job’s surface fields to fsaverage5 after simulation for comparisons across subjects." />
            </div>
          </section>
        </div>
      <ConductivityDialog
        open={tissueOpen}
        onOpenChange={setTissueOpen}
        value={draft.customConductivities as CustomConductivities}
        onSave={(value) => setDraft({ ...draft, customConductivities: value })}
      />
  </>;
}
