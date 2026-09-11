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
import type { JobSettings, SelectedRow } from "./types";
import { SimulationSettings } from "./SimulationSettings";

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
        <SimulationSettings value={draft} onChange={setDraft} />
      </Dialog>
    </>
  );
}
