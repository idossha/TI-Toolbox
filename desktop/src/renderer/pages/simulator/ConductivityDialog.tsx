import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { Dialog } from "../../ui/Overlay";
import { Button } from "../../ui/Button";
import { NumberInput } from "../../ui/NumberInput";
import { Callout } from "../../ui/Feedback";
import { TISSUE_TABLE } from "./types";

/** Tissue number -> conductivity override (S/m). Mirrors `tit.gui.components.conductivity_dialog`. */
export type CustomConductivities = Record<number, number>;

function seedRows(overrides: CustomConductivities): Record<number, number> {
  const seeded: Record<number, number> = {};
  for (const t of TISSUE_TABLE) seeded[t.number] = overrides[t.number] ?? t.defaultValue;
  return seeded;
}

/**
 * Editable table of tissue conductivities. Parity note (PARITY.md): the legacy dialog applies
 * overrides via `TISSUE_COND_<n>` environment variables read by `tit.sim.base`; `SimulationConfig`
 * has no `tissue_conductivities` field yet, so this is a real backend gap (reported) — the UI
 * collects and forwards the values under that name so nothing needs to change here once the field
 * lands.
 */
export function ConductivityDialog({
  open,
  onOpenChange,
  value,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: CustomConductivities;
  onSave: (value: CustomConductivities) => void;
}) {
  const [rows, setRows] = useState<Record<number, number>>(() => seedRows(value));
  // Re-seed when the dialog opens for a (possibly new) `value`, without an effect: adjusting
  // state during render from a prop change is the React-endorsed alternative to
  // `useEffect(() => setState(...), [prop])` (react-hooks/set-state-in-effect).
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) setRows(seedRows(value));
  }

  const invalid = Object.values(rows).some((v) => !(v > 0));

  function reset() {
    setRows(seedRows({}));
  }

  function save() {
    if (invalid) return;
    // Only keep overrides that actually differ from the default — an empty object means "use defaults".
    const overrides: CustomConductivities = {};
    for (const t of TISSUE_TABLE) {
      const v = rows[t.number];
      if (v !== undefined && v !== t.defaultValue) overrides[t.number] = v;
    }
    onSave(overrides);
    onOpenChange(false);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Tissue conductivity editor"
      description="Override the default tissue conductivities used by the solver. Values apply to every montage in this run."
      footer={
        <>
          <Button variant="ghost" icon={<RotateCcw size={14} />} onClick={reset}>
            Reset to defaults
          </Button>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} disabled={invalid}>
            Save conductivities
          </Button>
        </>
      }
    >
      {invalid && <Callout kind="danger">Every conductivity must be a positive number.</Callout>}
      <div className="data-table-container scroll-x">
        <table className="data-table">
          <thead>
            <tr>
              <th>Tissue</th>
              <th>Name</th>
              <th data-align="right">Value (S/m)</th>
              <th>Reference</th>
            </tr>
          </thead>
          <tbody>
            {TISSUE_TABLE.map((t) => (
              <tr key={t.number}>
                <td className="mono">{t.number}</td>
                <td>{t.name}</td>
                <td data-align="right">
                  <NumberInput
                    value={rows[t.number]}
                    onValueChange={(v) => setRows((r) => ({ ...r, [t.number]: v ?? 0 }))}
                    min={0}
                    step={0.001}
                    invalid={!((rows[t.number] ?? 0) > 0)}
                    aria-label={`${t.name} conductivity`}
                  />
                </td>
                <td className="text-dense" style={{ color: "var(--ink-2)" }}>
                  {t.reference}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Dialog>
  );
}
