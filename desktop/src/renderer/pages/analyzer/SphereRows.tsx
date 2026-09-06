/**
 * Multi-sphere table (x, y, z, radius), one row per sphere. Mirrors `spheres_table` in
 * `tit/gui/analyzer_tab.py`: a single row reproduces the classic single-sphere analysis exactly;
 * extra rows each become a separate `AnalyzerConfig` / job on Run (see PARITY.md).
 */
import { Plus, Trash2 } from "lucide-react";
import { Button, IconButton } from "../../ui/Button";
import { NumberInput } from "../../ui/NumberInput";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Field } from "../../ui/Field";

export interface Sphere {
  x: number | undefined;
  y: number | undefined;
  z: number | undefined;
  radius: number | undefined;
}

export const EMPTY_SPHERE: Sphere = {
  x: undefined,
  y: undefined,
  z: undefined,
  radius: undefined,
};

export function SphereRows({
  spheres,
  onSpheresChange,
  coordinateSpace,
  onCoordinateSpaceChange,
  allowMultiple = true,
  onOpenViewer,
  viewerLabel,
}: {
  spheres: Sphere[];
  onSpheresChange: (spheres: Sphere[]) => void;
  coordinateSpace: "subject" | "mni";
  onCoordinateSpaceChange: (space: "subject" | "mni") => void;
  /** Group mode uses exactly one sphere row — Add/Remove hidden (PARITY.md). */
  allowMultiple?: boolean;
  onOpenViewer?: () => void;
  viewerLabel?: string;
}) {
  function updateRow(i: number, patch: Partial<Sphere>) {
    onSpheresChange(
      spheres.map((s, idx) => (idx === i ? { ...s, ...patch } : s)),
    );
  }
  function removeRow(i: number) {
    if (spheres.length <= 1) return;
    onSpheresChange(spheres.filter((_, idx) => idx !== i));
  }

  return (
    <div className="form-grid" style={{ gridTemplateColumns: "1fr" }}>
      <Field
        label="Coordinate space"
        help={
          coordinateSpace === "mni"
            ? "MNI coordinates are transformed to each subject's native space before analysis."
            : "Subject-specific RAS coordinates."
        }
      >
        <SegmentedControl
          aria-label="Coordinate space"
          value={coordinateSpace}
          onValueChange={(v) => onCoordinateSpaceChange(v as "subject" | "mni")}
          options={[
            { value: "subject", label: "Subject" },
            { value: "mni", label: "MNI" },
          ]}
        />
      </Field>

      <Field
        label={
          allowMultiple
            ? "Spheres (x, y, z, radius)"
            : "Sphere (x, y, z, radius)"
        }
        help={
          allowMultiple
            ? "Each row is a sphere in mm. A single row behaves like the classic single-sphere analysis; additional rows each run as a separate analysis."
            : "Group analysis uses one shared sphere for every selected subject."
        }
      >
        <div className="data-table-container scroll-x">
          <table className="data-table" data-testid="sphere-table">
            <thead>
              <tr>
                <th>X (mm)</th>
                <th>Y (mm)</th>
                <th>Z (mm)</th>
                <th>Radius (mm)</th>
                <th aria-hidden />
              </tr>
            </thead>
            <tbody>
              {spheres.map((s, i) => (
                <tr key={i}>
                  <td>
                    <NumberInput
                      value={s.x}
                      onValueChange={(v) => updateRow(i, { x: v })}
                      step={0.1}
                      aria-label={`Sphere ${i + 1} X`}
                    />
                  </td>
                  <td>
                    <NumberInput
                      value={s.y}
                      onValueChange={(v) => updateRow(i, { y: v })}
                      step={0.1}
                      aria-label={`Sphere ${i + 1} Y`}
                    />
                  </td>
                  <td>
                    <NumberInput
                      value={s.z}
                      onValueChange={(v) => updateRow(i, { z: v })}
                      step={0.1}
                      aria-label={`Sphere ${i + 1} Z`}
                    />
                  </td>
                  <td>
                    <NumberInput
                      value={s.radius}
                      onValueChange={(v) => updateRow(i, { radius: v })}
                      step={0.5}
                      min={0}
                      aria-label={`Sphere ${i + 1} radius`}
                    />
                  </td>
                  <td>
                    {allowMultiple && spheres.length > 1 && (
                      <IconButton
                        aria-label={`Remove sphere ${i + 1}`}
                        icon={<Trash2 size={14} />}
                        variant="ghost"
                        onClick={() => removeRow(i)}
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Field>

      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        {allowMultiple && (
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus size={14} />}
            onClick={() => onSpheresChange([...spheres, { ...EMPTY_SPHERE }])}
          >
            Add sphere
          </Button>
        )}
        {onOpenViewer && (
          <Button variant="secondary" size="sm" onClick={onOpenViewer}>
            {viewerLabel ?? "Open in viewer"}
          </Button>
        )}
      </div>
    </div>
  );
}
