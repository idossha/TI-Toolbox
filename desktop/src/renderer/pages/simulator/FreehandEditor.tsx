/**
 * Free-hand placements — the **author** side only.
 *
 * Maintainer, 2026-09-06: *"there is a button and if the user clicks on it, it opens up the menu.
 * It should not have its own section"* — so this is just the editor card, opened by the Jobs
 * table's "New placement" footer button exactly as "New montage" opens the montage editor
 * (`MontageManager`). Choosing a saved set is a job row's business (its Montage cell lists them),
 * which is why nothing here lists the existing configurations.
 *
 * The draft is page-session state, so closing the editor — or leaving the page — never discards an
 * unfinished placement.
 */
import { Plus, Trash2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, IconButton } from "../../ui/Button";
import { Field, TextInput } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { Card, CardHeader, CardBody } from "../../ui/Layout";
import { notify } from "../../ui/Toast";
import { putFreehand, type FreehandConfig } from "./api";
import { useFreehandDraft } from "./freehandDraft";


/** Matches `Montage.simulation_mode`: 2 or 4+ pairs, i.e. 4 or 8+ positions (an even count). */
function isValidPositionCount(n: number): boolean {
  return n % 2 === 0 && (n / 2 === 2 || n / 2 >= 4);
}

export function FreehandEditor({ subjects: selectedSubjects, onClose }: { subjects: string[]; onClose: () => void }) {
  const queryClient = useQueryClient();

  // One draft for the page (see `freehandDraft.tsx`): the 3-D pane writes into the same rows this
  // table edits, so a click on the scalp and a typed number are the same act.
  const {
    subject: editSubject,
    setSubject: setEditSubject,
    name,
    setName,
    positions,
    setPositions,
    remove,
    reset,
  } = useFreehandDraft();

  const activeEditSubject = editSubject ?? selectedSubjects[0];

  const save = useMutation({
    mutationFn: () => {
      // FreehandConfig.type is on-disk stim_configs semantics (unipolar/multipolar), not
      // xyz/label — U for a 2-pair (4-position) montage, M for 4+ pairs (8+ positions). See
      // contracts/openapi.v1.yaml's FreehandConfig doc comment / tit/catalog.py::_read_freehand_file.
      const type: FreehandConfig["type"] = positions.length / 2 >= 4 ? "M" : "U";
      return putFreehand(activeEditSubject!, name.trim(), { name: name.trim(), type, electrode_positions: positions });
    },
    onSuccess: () => {
      notify.success(`Saved free-hand configuration "${name.trim()}" for ${activeEditSubject}.`);
      reset();
      // The job row's Montage cell reads this key, so it picks the new set up straight away.
      void queryClient.invalidateQueries({ queryKey: ["freehand", activeEditSubject] });
      onClose();
    },
    onError: (err: unknown) => notify.error("Could not save the free-hand configuration.", err instanceof Error ? err.message : undefined),
  });

  const validCount = isValidPositionCount(positions.length);

  return (
    <Card>
      <CardHeader title="New free-hand placement" />
      <CardBody>
        <div className="form-grid">
          <Field label="Subject" htmlFor="sim-freehand-subject" required>
            <Select
              id="sim-freehand-subject"
              value={activeEditSubject}
              onValueChange={setEditSubject}
              options={selectedSubjects.map((s) => ({ value: s, label: s }))}
              placeholder="Choose a subject"
              disabled={selectedSubjects.length === 0}
            />
          </Field>
          <Field label="Configuration name" htmlFor="sim-freehand-name" required>
            <TextInput id="sim-freehand-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. custom_4electrode" />
          </Field>
        </div>
        <div className="data-table-container scroll-x" style={{ marginTop: "var(--space-3)" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Label</th>
                <th data-align="right">X (mm)</th>
                <th data-align="right">Y (mm)</th>
                <th data-align="right">Z (mm)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, i) => (
                <tr key={i}>
                  <td className="mono">{i + 1}</td>
                  <td>
                    <TextInput
                      value={pos.label ?? ""}
                      aria-label={`Position ${i + 1} label`}
                      placeholder="optional"
                      onChange={(e) => setPositions((p) => p.map((row, idx) => (idx === i ? { ...row, label: e.target.value } : row)))}
                    />
                  </td>
                  {(["x", "y", "z"] as const).map((axis) => (
                    <td key={axis} data-align="right">
                      <NumberInput
                        value={pos[axis]}
                        step={0.1}
                        onValueChange={(v) => setPositions((p) => p.map((row, idx) => (idx === i ? { ...row, [axis]: v ?? 0 } : row)))}
                        aria-label={`Position ${i + 1} ${axis.toUpperCase()}`}
                      />
                    </td>
                  ))}
                  <td>
                    <IconButton
                      aria-label={`Remove position ${i + 1}`}
                      icon={<Trash2 size={14} />}
                      disabled={positions.length <= 2}
                      /* Removing a row renumbers the rest (2.5.0's `deleteChecked`) and drops its
                         dot from the pane, because the dots are derived from these rows. */
                      onClick={() => remove(i)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!validCount && <span className="field-error">Use 4 positions (2 pairs, standard TI) or 8 or more (4+ pairs, multi-channel mTI).</span>}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-3)" }}>
          <Button variant="ghost" size="sm" icon={<Plus size={14} />} onClick={() => setPositions((p) => [...p, { label: "", x: 0, y: 0, z: 0 }])}>
            Add position
          </Button>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={save.isPending}
              disabled={!activeEditSubject || !name.trim() || !validCount || positions.some((p) => p.x === undefined || p.y === undefined || p.z === undefined)}
              onClick={() => save.mutate()}
            >
              Save placement
            </Button>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
