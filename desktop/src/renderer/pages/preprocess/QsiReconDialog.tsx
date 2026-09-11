import { useState } from "react";
import "./qsi-dialogs.css";
import { Button } from "../../ui/Button";
import { Field, TextInput } from "../../ui/Field";
import { Checkbox } from "../../ui/Toggle";
import { Dialog } from "../../ui/Overlay";
import type { QsiReconSettings } from "./api";
import {
  ATLAS_CATEGORIES,
  DEFAULT_RECON_SPEC,
  SPEC_CATEGORIES,
  defaultQsiReconConfig,
  type Category,
} from "./qsi";

function CategoryChecklist({
  categories,
  selected,
  onToggle,
}: {
  categories: Category[];
  selected: string[];
  onToggle: (value: string, on: boolean) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
      }}
    >
      {categories.map((cat) => (
        <div key={cat.title}>
          <p
            className="text-dense"
            style={{ fontWeight: 600, marginBottom: 2 }}
          >
            {cat.title}
          </p>
          {cat.hint && (
            <p className="field-help" style={{ marginBottom: 4 }}>
              {cat.hint}
            </p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {cat.items.map((item) => (
              // The reconstruction pipelines are a long list of one-liners, so each row keeps its
              // description as the native `title` (no custom hover overlay — see ui/HelpPopover).
              <span key={item.value} title={item.tooltip}>
                <Checkbox
                  checked={selected.includes(item.value)}
                  onCheckedChange={(on) => onToggle(item.value, on)}
                  label={item.label}
                />
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function QsiReconDialog({
  open,
  onOpenChange,
  initial,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial: QsiReconSettings;
  onSave: (config: QsiReconSettings) => void;
}) {
  const [draft, setDraft] = useState<QsiReconSettings>(initial);
  // Reset the draft to `initial` on every open, without an effect (which would cascade an
  // extra render on every prop change). This is React's documented "adjust state during
  // rendering" pattern: a synchronous state adjustment while rendering, tracked via a
  // previous-value ref-in-state, runs once per actual open transition.
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) setDraft(initial);
  }

  const specs = draft.recon_specs ?? [DEFAULT_RECON_SPEC];
  const atlases = draft.atlases ?? [];

  function toggleSpec(value: string, on: boolean) {
    setDraft((d) => ({
      ...d,
      recon_specs: on ? [...specs, value] : specs.filter((s) => s !== value),
    }));
  }
  function toggleAtlas(value: string, on: boolean) {
    const next = on ? [...atlases, value] : atlases.filter((a) => a !== value);
    setDraft((d) => ({ ...d, atlases: next.length ? next : null }));
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="QSIRecon configuration"
      description="Reconstruction specifications and connectivity atlases, run via Docker."
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => setDraft(defaultQsiReconConfig())}
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
            Save QSIRecon configuration
          </Button>
        </>
      }
    >
      <div className="qsi-dialog-body qsi-recon-body">
        <p className="text-eyebrow" style={{ marginBottom: "var(--space-2)" }}>
          Reconstruction specifications
        </p>
        <CategoryChecklist
          categories={SPEC_CATEGORIES}
          selected={specs}
          onToggle={toggleSpec}
        />

        <p
          className="text-eyebrow"
          style={{ margin: "var(--space-4) 0 var(--space-1)" }}
        >
          Atlases for connectivity (optional)
        </p>
        <p className="field-help" style={{ marginBottom: "var(--space-2)" }}>
          Not required for the DTI-to-SimNIBS workflow.
        </p>
        <CategoryChecklist
          categories={ATLAS_CATEGORIES}
          selected={atlases}
          onToggle={toggleAtlas}
        />

        <p className="field-help">
          CPU, memory, and OpenMP defaults are configured in Settings →
          Pre-processing.
        </p>

        <div style={{ marginTop: "var(--space-4)" }}>
          <p
            className="text-eyebrow"
            style={{ marginBottom: "var(--space-2)" }}
          >
            Options
          </p>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-2)",
            }}
          >
            <Checkbox
              checked={draft.use_gpu}
              onCheckedChange={(v) => setDraft((d) => ({ ...d, use_gpu: v }))}
              label="Use GPU (requires NVIDIA Docker runtime)"
            />
            <Checkbox
              checked={draft.skip_odf_reports}
              onCheckedChange={(v) =>
                setDraft((d) => ({ ...d, skip_odf_reports: v }))
              }
              label="Skip ODF report generation"
            />
          </div>
        </div>

        <div style={{ marginTop: "var(--space-4)" }}>
          <Field label="Image tag" help="Docker image tag for QSIRecon.">
            <TextInput
              value={draft.image_tag}
              onChange={(e) =>
                setDraft((d) => ({ ...d, image_tag: e.target.value }))
              }
            />
          </Field>
        </div>
      </div>
    </Dialog>
  );
}
