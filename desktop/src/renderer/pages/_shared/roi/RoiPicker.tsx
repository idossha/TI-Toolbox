/**
 * Shared ROI picker for the optimizer pages (flex-search owns this file; ex-search/mex-search and
 * the analyzer import it — see `desktop/README` lane notes). Parity source:
 * `tit/gui/components/roi_picker.py` (`ROIPickerWidget`).
 *
 * Three modes, one at a time via `modes`: spherical (a table of x/y/z/radius rows — multiple rows
 * union into one combined target), cortical (a FreeSurfer `.annot` atlas + region chips, searched
 * by name), subcortical (a volumetric atlas, Subject/MNI space, region chips, tissue compartment).
 * Multi-selecting regions/spheres *is* combining — flex-search's ROI classes take a region/sphere
 * list natively (see `types.ts`), unlike ex-search's separate Combine toggle.
 *
 * `GET /api/catalog/atlases/regions` returns `Region { id: integer, name, hemi: "lh"|"rh"|null }`
 * (reconciled fix:contract 2026-08-27 — was `id: string | number` with no `hemi`); `id` is exactly
 * the FreeSurfer `.annot` label index / volumetric atlas voxel label `AtlasROI.label` /
 * `SubcorticalROI.label` need, and cortical `hemi` is that region's own hemisphere. The mock's
 * `atlas_regions.json` fixture already returns this shape (verified in this lane). REMAINING GAP
 * (reported to the orchestrator, out of P3's lane): the real `tit/catalog.py::atlas_regions`'s
 * cortical branch still returns a display-string id with no `hemi` — cortical ROIs won't resolve
 * correctly end-to-end against the real server until B2 lands the integer label + hemi there too.
 */
import { useMemo, useState } from "react";
import { Compass, Plus, Target, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Field, TextInput } from "../../../ui/Field";
import { NumberInput } from "../../../ui/NumberInput";
import { Select } from "../../../ui/Select";
import { Combobox } from "../../../ui/Combobox";
import { SelectionPicker, type SelectionItem } from "../../../ui/SelectionList";
import { Checkbox } from "../../../ui/Toggle";
import { SegmentedControl } from "../../../ui/SegmentedControl";
import { regionKey } from "../scene/model";
import { Button, IconButton } from "../../../ui/Button";
import { Skeleton, Callout } from "../../../ui/Feedback";
import { Dialog, AlertDialog } from "../../../ui/Overlay";
import { CoordinateInput, type Coordinate } from "../../../ui/CoordinateInput";
import { notify } from "../../../ui/Toast";
import { getAtlases, getAtlasRegions, getRois, saveRoi, deleteRoi, type Roi } from "./api";
import "./roi.css";
import {
  emptyRoi,
  emptySphereRow,
  type RoiMode,
  type RoiRegion,
  type RoiSpace,
  type RoiValue,
  type TissueKind,
} from "./types";

const TISSUE_OPTIONS = [
  { value: "GM", label: "Gray matter (GM)" },
  { value: "WM", label: "White matter (WM)" },
  { value: "both", label: "GM + WM (both)" },
];

const SPACE_OPTIONS = [
  { value: "subject", label: "Subject" },
  { value: "mni", label: "MNI" },
];

/** Canonical ROI-type order across every picker on the site (DESIGN QA vocabulary pass).
 *  `saved` leads because it is the ex/mEx default; it is absent from flex's `modes`, so flex's
 *  own order (cortical, subcortical, spherical) is unchanged. */
const MODE_ORDER: RoiMode[] = ["saved", "cortical", "subcortical", "spherical"];
const MODE_LABEL: Record<RoiMode, string> = {
  saved: "Saved",
  cortical: "Cortical",
  subcortical: "Subcortical",
  spherical: "Spherical",
};

/**
 * The region key comes from the **scene model**, not from a second copy here (N3).
 *
 * `<ScenePane>` and this picker edit the SAME list — a 3D click and a chip in the form are one
 * selection, in both directions — and they compare regions with one function to make that true
 * rather than merely intended. Two identical-looking key functions is how a region ends up
 * selected in the pane and absent from the config that runs.
 */

export interface RoiPickerProps {
  value: RoiValue;
  onChange: (value: RoiValue) => void;
  modes: RoiMode[];
  subject: string | undefined;
  /** Seeds the coordinate/atlas space for a freshly-created value; the value's own `space` /
   *  `atlasSpace` field is the source of truth once set (see `types.ts`). */
  space?: RoiSpace;
  disabled?: boolean;
  /** Renders "Open T1 in viewer" in spherical mode; omit to hide it (e.g. for a non-ROI picker
   *  that never needs its own viewer launcher). The picker stays presentational — the host page
   *  owns the ViewSpec/job call. */
  onOpenViewer?: () => void;
  /** `saved` mode only: mEx never unions selected ROIs (its run path has no combined mode), so
   *  the Optimizer hides the checkbox on that method rather than showing a dead control. */
  allowCombine?: boolean;
}

export function RoiPicker({ value, onChange, modes, subject, space = "subject", disabled, onOpenViewer, allowCombine }: RoiPickerProps) {
  function setMode(mode: RoiMode) {
    if (mode === value.mode) return;
    onChange(emptyRoi(mode, space));
  }

  return (
    <div className="roi-picker" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {modes.length > 1 && (
        <SegmentedControl
          aria-label="ROI type"
          value={value.mode}
          onValueChange={(v) => setMode(v as RoiMode)}
          options={MODE_ORDER.filter((m) => modes.includes(m)).map((m) => ({ value: m, label: MODE_LABEL[m] }))}
        />
      )}
      {value.mode === "spherical" && (
        <SphericalPanel value={value} onChange={onChange} disabled={disabled} onOpenViewer={onOpenViewer} />
      )}
      {value.mode === "cortical" && <CorticalPanel value={value} onChange={onChange} subject={subject} disabled={disabled} />}
      {value.mode === "subcortical" && <SubcorticalPanel value={value} onChange={onChange} subject={subject} disabled={disabled} />}
      {value.mode === "saved" && <SavedPanel value={value} onChange={onChange} subject={subject} disabled={disabled} allowCombine={allowCombine} />}
    </div>
  );
}

function AddRoiDialog({
  open,
  onOpenChange,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (roi: Roi) => void;
}) {
  const [name, setName] = useState("");
  const [coord, setCoord] = useState<Coordinate>({ x: 0, y: 0, z: 0 });
  const [space, setSpace] = useState<RoiSpace>("subject");
  const canSave = name.trim().length > 0 && coord.x !== undefined && coord.y !== undefined && coord.z !== undefined;
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add new ROI"
      description="Coordinates in RAS millimeters."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!canSave}
            onClick={() => {
              onSave({ name: name.trim(), x: coord.x ?? 0, y: coord.y ?? 0, z: coord.z ?? 0, space });
              setName("");
              setCoord({ x: 0, y: 0, z: 0 });
              onOpenChange(false);
            }}
          >
            Save ROI
          </Button>
        </>
      }
    >
      <div className="form-grid">
        <Field label="ROI name" htmlFor="add-roi-name" required>
          <TextInput id="add-roi-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. L_Insula_target" />
        </Field>
        <Field label="Coordinates">
          <CoordinateInput value={coord} onValueChange={setCoord} space={space} onSpaceChange={(s) => setSpace(s as RoiSpace)} />
        </Field>
      </div>
    </Dialog>
  );
}

/**
 * The ex/mEx target list: saved ROI CSVs for this subject, each selectable, plus the radius,
 * coordinate space and the "combine into one target" union flag. Fetches and mutates
 * `/api/catalog/rois` itself, exactly as the atlas panels fetch their atlases — the caller passes
 * a subject, not a data set.
 */
function SavedPanel({
  value,
  onChange,
  subject,
  disabled,
  allowCombine = true,
}: {
  value: Extract<RoiValue, { mode: "saved" }>;
  onChange: (v: RoiValue) => void;
  subject: string | undefined;
  disabled?: boolean;
  allowCombine?: boolean;
}) {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const rois = useQuery({
    queryKey: ["rois", subject],
    queryFn: () => getRois(subject as string),
    enabled: subject !== undefined,
  });

  const add = useMutation({
    mutationFn: (roi: Roi) => saveRoi(subject as string, roi),
    onSuccess: () => {
      notify.success("ROI saved.");
      void queryClient.invalidateQueries({ queryKey: ["rois", subject] });
    },
    onError: () => notify.error("Could not save the ROI."),
  });
  const remove = useMutation({
    mutationFn: (name: string) => deleteRoi(subject as string, name),
    onSuccess: (_data, name) => {
      notify.success("ROI removed.");
      onChange({ ...value, selected: value.selected.filter((n) => n !== name) });
      void queryClient.invalidateQueries({ queryKey: ["rois", subject] });
    },
    onError: () => notify.error("Could not remove the ROI."),
  });

  function toggle(name: string, on: boolean) {
    onChange({ ...value, selected: on ? [...value.selected, name] : value.selected.filter((n) => n !== name) });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      {rois.isFetching && <Skeleton height={64} />}
      {rois.error && <Callout kind="danger">Could not load saved ROIs for this subject.</Callout>}
      {!rois.isFetching && !rois.error && (
        <div className="roi-picker-list" role="group" aria-label="Saved ROIs">
          {(rois.data ?? []).map((r) => (
            <label key={r.name} className="roi-saved-row">
              <Checkbox checked={value.selected.includes(r.name)} onCheckedChange={(on) => toggle(r.name, on)} disabled={disabled} />
              <Target size={12} aria-hidden />
              <span className="text-dense mono">{r.name}</span>
              <span className="field-help tabular">
                {r.x.toFixed(1)}, {r.y.toFixed(1)}, {r.z.toFixed(1)} mm ({r.space})
              </span>
              <IconButton
                aria-label={`Remove ROI ${r.name}`}
                icon={<Trash2 size={12} />}
                variant="ghost"
                size="sm"
                disabled={disabled}
                onClick={() => setPendingDelete(r.name)}
              />
            </label>
          ))}
          {(rois.data ?? []).length === 0 && <p className="field-help">No saved ROIs for this subject yet.</p>}
        </div>
      )}
      <div className="form-grid">
        <Field label="Radius" help="Radius of the spherical target used for field extraction.">
          <NumberInput
            value={value.radius}
            onValueChange={(v) => onChange({ ...value, radius: v ?? 3.0 })}
            unit="mm"
            min={1}
            max={10}
            step={0.5}
            disabled={disabled}
          />
        </Field>
        <Field label="Space" help="Space of the saved ROI centres. MNI centres are transformed to subject space before the search runs.">
          <SegmentedControl
            aria-label="Coordinate space"
            value={value.space}
            onValueChange={(v) => onChange({ ...value, space: v as RoiSpace })}
            options={SPACE_OPTIONS}
          />
        </Field>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <Button variant="ghost" size="sm" icon={<Plus size={14} />} disabled={disabled || subject === undefined} onClick={() => setAddOpen(true)}>
          Add ROI
        </Button>
        {allowCombine && (
          <Checkbox
            checked={value.combine}
            onCheckedChange={(on) => onChange({ ...value, combine: on })}
            disabled={disabled}
            label="Combine selected ROIs into one target"
          />
        )}
      </div>
      <AddRoiDialog open={addOpen} onOpenChange={setAddOpen} onSave={(roi) => add.mutate(roi)} />
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete ROI"
        description={`Delete "${pendingDelete}"? This cannot be undone.`}
        confirmLabel="Delete ROI"
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete);
          setPendingDelete(null);
        }}
      />
    </div>
  );
}

function SphericalPanel({
  value,
  onChange,
  disabled,
  onOpenViewer,
}: {
  value: Extract<RoiValue, { mode: "spherical" }>;
  onChange: (v: RoiValue) => void;
  disabled?: boolean;
  onOpenViewer?: () => void;
}) {
  function updateRow(i: number, patch: Partial<(typeof value.spheres)[number]>) {
    onChange({ ...value, spheres: value.spheres.map((s, idx) => (idx === i ? { ...s, ...patch } : s)) });
  }
  function removeRow(i: number) {
    onChange({ ...value, spheres: value.spheres.filter((_, idx) => idx !== i) });
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-2)" }}>
        <Field label="Space">
          <SegmentedControl
            aria-label="Coordinate space"
            value={value.space}
            onValueChange={(v) => onChange({ ...value, space: v as RoiSpace })}
            options={SPACE_OPTIONS}
          />
        </Field>
        {onOpenViewer && (
          <Button variant="secondary" size="sm" icon={<Compass size={14} />} disabled={disabled} onClick={onOpenViewer}>
            Open T1 in viewer
          </Button>
        )}
      </div>
      <div className="scroll-x">
        <table className="data-table">
          <thead>
            <tr>
              <th>X (mm)</th>
              <th>Y (mm)</th>
              <th>Z (mm)</th>
              <th>Radius (mm)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {value.spheres.map((row, i) => (
              <tr key={i}>
                <td>
                  <NumberInput value={row.x} onValueChange={(v) => updateRow(i, { x: v })} step={0.1} disabled={disabled} aria-label={`Sphere ${i + 1} X`} />
                </td>
                <td>
                  <NumberInput value={row.y} onValueChange={(v) => updateRow(i, { y: v })} step={0.1} disabled={disabled} aria-label={`Sphere ${i + 1} Y`} />
                </td>
                <td>
                  <NumberInput value={row.z} onValueChange={(v) => updateRow(i, { z: v })} step={0.1} disabled={disabled} aria-label={`Sphere ${i + 1} Z`} />
                </td>
                <td>
                  <NumberInput value={row.radius} onValueChange={(v) => updateRow(i, { radius: v })} step={1} min={0.1} disabled={disabled} aria-label={`Sphere ${i + 1} radius`} />
                </td>
                <td>
                  <IconButton aria-label={`Remove sphere ${i + 1}`} icon={<Trash2 size={14} />} disabled={disabled} onClick={() => removeRow(i)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button variant="ghost" size="sm" icon={<Plus size={14} />} disabled={disabled} onClick={() => onChange({ ...value, spheres: [...value.spheres, emptySphereRow()] })}>
        Add sphere
      </Button>
      <p className="field-help">Each row is a sphere. Multiple rows union into one combined target.</p>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <Checkbox
          checked={value.volumetric}
          onCheckedChange={(v) => onChange({ ...value, volumetric: v })}
          disabled={disabled}
          label="Volumetric (evaluate on volume tetrahedra instead of the cortical surface)"
        />
        {value.volumetric && (
          <Select
            value={value.tissues}
            onValueChange={(v) => onChange({ ...value, tissues: v as TissueKind })}
            options={TISSUE_OPTIONS}
            disabled={disabled}
          />
        )}
      </div>
    </div>
  );
}

function CorticalPanel({
  value,
  onChange,
  subject,
  disabled,
}: {
  value: Extract<RoiValue, { mode: "cortical" }>;
  onChange: (v: RoiValue) => void;
  subject: string | undefined;
  disabled?: boolean;
}) {
  const atlases = useQuery({
    queryKey: ["atlases", subject, "cortical"],
    queryFn: () => getAtlases(subject as string, "cortical"),
    enabled: subject !== undefined,
  });
  const lhRegions = useQuery({
    queryKey: ["atlas-regions", subject, value.atlas, "lh"],
    queryFn: () => getAtlasRegions(subject as string, value.atlas as string, "lh"),
    enabled: subject !== undefined && value.atlas !== undefined,
  });
  const rhRegions = useQuery({
    queryKey: ["atlas-regions", subject, value.atlas, "rh"],
    queryFn: () => getAtlasRegions(subject as string, value.atlas as string, "rh"),
    enabled: subject !== undefined && value.atlas !== undefined,
  });

  const options = useMemo(() => {
    // `r.hemi` is the region's own authoritative hemisphere (Region schema); fall back to the
    // per-hemisphere query context in case a not-yet-updated backend still returns `null` for
    // cortical regions (see the header comment's REMAINING GAP).
    const lh = (lhRegions.data ?? []).map((r) => ({ value: `lh:${r.id}`, label: `L · ${r.name}`, region: { id: r.id, name: r.name, hemi: (r.hemi ?? "lh") as "lh" | "rh" } }));
    const rh = (rhRegions.data ?? []).map((r) => ({ value: `rh:${r.id}`, label: `R · ${r.name}`, region: { id: r.id, name: r.name, hemi: (r.hemi ?? "rh") as "lh" | "rh" } }));
    return [...lh, ...rh];
  }, [lhRegions.data, rhRegions.data]);

  const selectedKeys = value.regions.map(regionKey);
  const regionItems: SelectionItem[] = options.map((o) => ({ id: o.value, label: o.label, search: o.label }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <Field label="Atlas" required>
        {atlases.isFetching ? (
          <Skeleton height={32} />
        ) : (
          <Combobox
            value={value.atlas}
            onValueChange={(atlas) => onChange({ ...value, atlas, regions: [] })}
            options={(atlases.data ?? []).map((a) => ({ value: a.id, label: a.name }))}
            placeholder="Select an atlas…"
            searchPlaceholder="Search atlases…"
            disabled={disabled || subject === undefined}
          />
        )}
      </Field>
      <Field label="Region(s)" required help="Multiple regions union into one combined target. Search by name; the picker lists both hemispheres.">
        {/* One grammar (plan C1): an atlas has 68-360 regions, so this is the same list the subject
            table and the ex buckets are — filter, ⇧-range over neighbouring regions, All · None,
            `N of M selected` — rather than a chip combobox that could only add one region per
            popover and truncated the answer to two chips. */}
        <SelectionPicker
          items={regionItems}
          value={selectedKeys}
          onChange={(keys) => {
            const byKey = new Map<string, RoiRegion>(options.map((o) => [o.value, o.region]));
            onChange({ ...value, regions: keys.map((k) => byKey.get(k)).filter((r): r is RoiRegion => r !== undefined) });
          }}
          label="Regions"
          title="Choose regions"
          headers={{ label: "Region" }}
          filterPlaceholder="Filter regions…"
          idPrefix="roi-region"
          placeholder={value.atlas ? "Add region…" : "Select an atlas first"}
          disabled={disabled || value.atlas === undefined}
        />
      </Field>
      {(lhRegions.error || rhRegions.error) && <Callout kind="danger">Could not load regions for this atlas.</Callout>}
    </div>
  );
}

function SubcorticalPanel({
  value,
  onChange,
  subject,
  disabled,
}: {
  value: Extract<RoiValue, { mode: "subcortical" }>;
  onChange: (v: RoiValue) => void;
  subject: string | undefined;
  disabled?: boolean;
}) {
  const atlases = useQuery({
    queryKey: ["atlases", subject, "subcortical", value.atlasSpace],
    queryFn: () => getAtlases(subject as string, "subcortical", value.atlasSpace),
    enabled: subject !== undefined,
  });
  const regions = useQuery({
    queryKey: ["atlas-regions", subject, value.atlas],
    queryFn: () => getAtlasRegions(subject as string, value.atlas as string),
    enabled: subject !== undefined && value.atlas !== undefined,
  });
  const options = (regions.data ?? []).map((r) => ({ value: String(r.id), label: r.name, region: { id: r.id, name: r.name } }));
  const selectedKeys = value.regions.map((r) => String(r.id));
  const regionItems: SelectionItem[] = options.map((o) => ({ id: o.value, label: o.label, search: o.label }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <Field label="Space">
        <SegmentedControl
          aria-label="Atlas space"
          value={value.atlasSpace}
          onValueChange={(v) => onChange({ ...value, atlasSpace: v as RoiSpace, atlas: undefined, regions: [] })}
          options={SPACE_OPTIONS}
        />
      </Field>
      <Field label="Tissue type" help="Tissue compartment(s) to include when evaluating the volume ROI.">
        <Select value={value.tissues} onValueChange={(v) => onChange({ ...value, tissues: v as TissueKind })} options={TISSUE_OPTIONS} disabled={disabled} />
      </Field>
      <Field label="Volume atlas" required>
        {atlases.isFetching ? (
          <Skeleton height={32} />
        ) : (
          <Combobox
            value={value.atlas}
            onValueChange={(atlas) => onChange({ ...value, atlas, regions: [] })}
            options={(atlases.data ?? []).map((a) => ({ value: a.id, label: a.name }))}
            placeholder="Select a volume atlas…"
            searchPlaceholder="Search atlases…"
            disabled={disabled || subject === undefined}
          />
        )}
      </Field>
      <Field label="Region(s)" required help="Multiple regions union into one combined target (e.g. both hippocampi).">
        {/* One grammar (plan C1): an atlas has 68-360 regions, so this is the same list the subject
            table and the ex buckets are — filter, ⇧-range over neighbouring regions, All · None,
            `N of M selected` — rather than a chip combobox that could only add one region per
            popover and truncated the answer to two chips. */}
        <SelectionPicker
          items={regionItems}
          value={selectedKeys}
          onChange={(keys) => {
            const byKey = new Map<string, RoiRegion>(options.map((o) => [o.value, o.region]));
            onChange({ ...value, regions: keys.map((k) => byKey.get(k)).filter((r): r is RoiRegion => r !== undefined) });
          }}
          label="Regions"
          title="Choose regions"
          headers={{ label: "Region" }}
          filterPlaceholder="Filter regions…"
          idPrefix="roi-region"
          placeholder={value.atlas ? "Add region…" : "Select an atlas first"}
          disabled={disabled || value.atlas === undefined}
        />
      </Field>
      {regions.error && <Callout kind="danger">Could not load regions for this atlas.</Callout>}
    </div>
  );
}
