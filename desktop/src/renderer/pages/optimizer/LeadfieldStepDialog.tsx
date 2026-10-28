/**
 * The step between "Generate leadfield" and the job: which electrode the leadfield is computed
 * with. A leadfield is the field of one electrode model at every position of the net, so its size
 * and gel are part of what it is, and an Ex search over it scores montages with them. Starts at
 * the toolbox defaults (`defaultLeadfieldElectrode`) every time it opens.
 */
import { useState } from "react";
import { Zap } from "lucide-react";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Overlay";
import { ElectrodeSettings, type ElectrodeGeometry } from "../_shared/electrodes/ElectrodeSettings";
import { defaultLeadfieldElectrode, type LeadfieldElectrode } from "./api";

export interface LeadfieldRequest {
  subject: string;
  net: string;
}

function geometryOf(e: LeadfieldElectrode): ElectrodeGeometry {
  const [w = 8, h = 8] = e.electrode_dimensions;
  return { electrodeShape: e.electrode_shape, dimensions: [w, h], gelThickness: e.gel_thickness };
}

/** Why the chosen electrode cannot be computed, or `null`. */
function invalidReason(g: ElectrodeGeometry): string | null {
  if (!g.dimensions.every((d) => Number.isFinite(d) && d > 0)) return "Width and height must be greater than 0 mm.";
  if (!(Number.isFinite(g.gelThickness) && g.gelThickness > 0)) return "Gel thickness must be greater than 0 mm.";
  return null;
}

export function LeadfieldStepDialog({
  request,
  onCancel,
  onConfirm,
}: {
  request: LeadfieldRequest | null;
  onCancel: () => void;
  onConfirm: (request: LeadfieldRequest, electrode: LeadfieldElectrode) => void;
}) {
  const [draft, setDraft] = useState<ElectrodeGeometry>(() => geometryOf(defaultLeadfieldElectrode()));
  // Re-seed on every open, without an effect (the pattern `JobSettingsDialog` uses).
  const [seededFor, setSeededFor] = useState<LeadfieldRequest | null>(null);
  if (request && request !== seededFor) {
    setSeededFor(request);
    setDraft(geometryOf(defaultLeadfieldElectrode()));
  }
  if (!request && seededFor !== null) setSeededFor(null);
  const invalid = invalidReason(draft);

  return (
    <Dialog
      open={!!request}
      onOpenChange={(open) => !open && onCancel()}
      title="Generate leadfield"
      description={request ? `${request.subject} · ${request.net}` : undefined}
      footer={
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", width: "100%" }}>
          {invalid && <span className="field-error">{invalid}</span>}
          <span style={{ marginLeft: "auto", display: "flex", gap: "var(--space-2)" }}>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
            <Button
              icon={<Zap size={14} />}
              disabled={!!invalid}
              onClick={() =>
                request &&
                onConfirm(request, {
                  ...defaultLeadfieldElectrode(),
                  electrode_shape: draft.electrodeShape,
                  electrode_dimensions: [...draft.dimensions],
                  gel_thickness: draft.gelThickness,
                })
              }
            >
              Generate
            </Button>
          </span>
        </div>
      }
    >
      <div className="leadfield-step" data-testid="leadfield-step">
        <p className="field-help" style={{ margin: "0 0 var(--space-3)" }}>
          The leadfield places this electrode at every position of the net, and an Ex search over it scores montages with this
          size and gel. A different electrode needs its own leadfield.
        </p>
        <ElectrodeSettings value={draft} onChange={setDraft} />
      </div>
    </Dialog>
  );
}
