/**
 * One job's own **electrodes · conductivity · output fields**.
 *
 * Maintainer, 2026-09-06, on the three page-level sections: *"This should be the default of the
 * simulator; however each job should have its own settings configuration that users configure per
 * job, instead of global settings applied automatically to all jobs."*
 *
 * So the page's sections are the **defaults for new jobs** and this dialog is where one job
 * disagrees with them. A row that has never been opened here carries no settings of its own and
 * follows the defaults live — which is what makes "change a default" reach exactly the rows that
 * never disagreed. `Reset to defaults` puts a row back into that state.
 *
 * The controls are deliberately the same ones the page's sections use (`SegmentedControl`,
 * `NumberInput`, `Select`, the output-field checkboxes and `ConductivityDialog`), so per-job and
 * default are the same form in two places rather than two forms that can drift.
 */
import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { Dialog } from "../../ui/Overlay";
import { Button } from "../../ui/Button";
import { HelpIcon } from "../../ui/HelpPopover";
import { Field } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Checkbox } from "../../ui/Toggle";
import { ConductivityDialog, type CustomConductivities } from "./ConductivityDialog";
import { CONDUCTIVITY_OPTIONS, OUTPUT_FIELDS, type JobSettings, type SelectedRow } from "./types";

export interface JobSettingsDialogProps {
  /** The row being edited; `null` closes the dialog. */
  row: SelectedRow | null;
  /** The page's defaults — what an untouched row runs with, and what `Reset` returns to. */
  defaults: JobSettings;
  onClose: () => void;
  /** `undefined` puts the row back on the defaults. */
  onSave: (settings: JobSettings | undefined) => void;
}

export function JobSettingsDialog({ row, defaults, onClose, onSave }: JobSettingsDialogProps) {
  const open = !!row;
  const [draft, setDraft] = useState<JobSettings>(defaults);
  const [tissueOpen, setTissueOpen] = useState(false);
  // Re-seed when the dialog opens on a row, without an effect (the pattern `ConductivityDialog`
  // already uses): adjusting state during render from a prop change is React's own answer to
  // `useEffect(() => setState(...), [prop])`.
  const [seededFor, setSeededFor] = useState<string | null>(null);
  if (row && seededFor !== row.id) {
    setSeededFor(row.id);
    setDraft(row.settings ?? defaults);
  }
  if (!row && seededFor !== null) setSeededFor(null);

  const invalid = draft.outputFields.length === 0;

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => !next && onClose()}
        title="Simulation"
        description={row ? `${row.subjectId || "no subject"} · ${row.name || "no montage"}` : undefined}
        footer={
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", width: "100%" }}>
            <Button
              variant="ghost"
              icon={<RotateCcw size={14} />}
              onClick={() => setDraft(defaults)}
              disabled={JSON.stringify(draft) === JSON.stringify(defaults)}
            >
              Reset to defaults
            </Button>
            <span style={{ marginLeft: "auto", display: "flex", gap: "var(--space-2)" }}>
              <Button variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button
                disabled={invalid}
                onClick={() => {
                  // Settings identical to the defaults are not "custom": the row goes back to
                  // following them, so a later change of a default still reaches it.
                  onSave(JSON.stringify(draft) === JSON.stringify(defaults) ? undefined : draft);
                }}
              >
                Done
              </Button>
            </span>
          </div>
        }
      >
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
      </Dialog>
      <ConductivityDialog
        open={tissueOpen}
        onOpenChange={setTissueOpen}
        value={draft.customConductivities as CustomConductivities}
        onSave={(value) => setDraft({ ...draft, customConductivities: value })}
      />
    </>
  );
}
