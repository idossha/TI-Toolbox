import { useState } from "react";
import "./qsi-dialogs.css";
import { Button } from "../../ui/Button";
import { Field, TextInput } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { Checkbox } from "../../ui/Toggle";
import { Dialog } from "../../ui/Overlay";
import type { QsiPrepSettings } from "./api";
import {
  DENOISE_METHODS,
  UNRINGING_METHODS,
  defaultQsiPrepConfig,
} from "./qsi";

const asOptions = (values: string[]) =>
  values.map((v) => ({ value: v, label: v }));

export function QsiPrepDialog({
  open,
  onOpenChange,
  initial,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial: QsiPrepSettings;
  onSave: (config: QsiPrepSettings) => void;
}) {
  const [draft, setDraft] = useState<QsiPrepSettings>(initial);
  // Reset the draft to `initial` on every open, without an effect (which would cascade an
  // extra render on every prop change). This is React's documented "adjust state during
  // rendering" pattern: a synchronous state adjustment while rendering, tracked via a
  // previous-value ref-in-state, runs once per actual open transition.
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) setDraft(initial);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="QSIPrep configuration"
      description="DWI preprocessing, run via Docker on an x86-64 (Linux or Windows) host; QSIPrep cannot run on Apple Silicon."
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => setDraft(defaultQsiPrepConfig())}
            style={{ marginRight: "auto" }}
          >
            Reset to defaults
          </Button>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              onSave(draft);
              onOpenChange(false);
            }}
          >
            Save QSIPrep configuration
          </Button>
        </>
      }
    >
      <div className="qsi-dialog-body qsi-prep-body">
        <div className="qsi-fields">
          <Field
            layout="stacked"
            label="Output resolution"
            help="Isotropic voxel size in mm. Leave empty for the DWI's native voxel size."
          >
            <NumberInput
              value={draft.output_resolution ?? undefined}
              onValueChange={(v) =>
                setDraft((d) => ({ ...d, output_resolution: v ?? null }))
              }
              placeholder="native"
              unit="mm"
              min={0.5}
              max={3.0}
              step={0.1}
            />
          </Field>
          <Field
            layout="stacked"
            label="Image tag"
            help="Docker image tag for QSIPrep."
          >
            <TextInput
              value={draft.image_tag}
              onChange={(e) =>
                setDraft((d) => ({ ...d, image_tag: e.target.value }))
              }
            />
          </Field>
        </div>

        <p className="field-help">
          Distortion correction is always on: TOPUP with a reverse
          phase-encoding fieldmap when the subject has one, otherwise
          fieldmap-less SyN. CPU, memory, and OpenMP defaults are configured in
          Settings → Pre-processing.
        </p>

        <div style={{ marginTop: "var(--space-4)" }}>
          <p
            className="text-eyebrow"
            style={{ marginBottom: "var(--space-2)" }}
          >
            Processing options
          </p>
          <div className="qsi-fields">
            <Field
              layout="stacked"
              label="Denoise method"
              help="Denoising method applied to DWI data."
            >
              <Select
                value={draft.denoise_method}
                onValueChange={(v) =>
                  setDraft((d) => ({ ...d, denoise_method: v }))
                }
                options={asOptions(DENOISE_METHODS)}
              />
            </Field>
            <Field
              layout="stacked"
              label="Unringing method"
              help="auto: rpg for partial-Fourier acquisitions, else mrdegibbs."
            >
              <Select
                value={draft.unringing_method}
                onValueChange={(v) =>
                  setDraft((d) => ({ ...d, unringing_method: v }))
                }
                options={asOptions(UNRINGING_METHODS)}
              />
            </Field>
          </div>
          <div style={{ marginTop: "var(--space-3)" }}>
            <Checkbox
              checked={draft.skip_bids_validation}
              onCheckedChange={(v) =>
                setDraft((d) => ({ ...d, skip_bids_validation: v }))
              }
              label="Skip BIDS validation (useful for non-BIDS datasets)"
            />
          </div>
          <div style={{ marginTop: "var(--space-2)" }}>
            <Checkbox
              checked={draft.mni_normalization ?? false}
              onCheckedChange={(v) =>
                setDraft((d) => ({ ...d, mni_normalization: v }))
              }
              label="MNI normalization (only needed for QSIRecon connectivity atlases)"
            />
          </div>
        </div>
      </div>
    </Dialog>
  );
}
