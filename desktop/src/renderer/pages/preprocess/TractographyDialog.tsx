/**
 * Tractography's **Configure…**, the sibling of `QsiPrepDialog`: what the row's checkbox will run
 * with. The atlas fixes the network's regions, so a new one needs a new connectome.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Dialog } from "../../ui/Overlay";
import { Select } from "../../ui/Select";
import { getAtlases } from "../_shared/roi/api";

export function TractographyDialog({ open, onOpenChange, subject, atlas, seeds, onSave }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Whose atlases to list; the first selected subject. */
  subject: string | undefined;
  atlas: string;
  seeds: number;
  onSave: (atlas: string, seeds: number) => void;
}) {
  const [draftAtlas, setDraftAtlas] = useState(atlas);
  const [draftSeeds, setDraftSeeds] = useState(seeds);
  useEffect(() => {
    if (open) {
      setDraftAtlas(atlas);
      setDraftSeeds(seeds);
    }
  }, [open, atlas, seeds]);
  const atlases = useQuery({
    queryKey: ["atlases", subject, "cortical", "subject"],
    queryFn: () => getAtlases(subject as string, "cortical", "subject"),
    enabled: open && !!subject,
  });
  const names = [...new Set([draftAtlas, ...(atlases.data ?? []).map((a) => a.id)])];
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Tractography"
      description="Whole-brain tracking and the region connectome, from QSIPrep output."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="primary"
            data-testid="tractography-save"
            onClick={() => {
              onSave(draftAtlas, draftSeeds);
              onOpenChange(false);
            }}
          >
            Save
          </Button>
        </>
      }
    >
      <div data-testid="tractography-form" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", minWidth: 360 }}>
        <Field label="Atlas" help="Streamline ends are labelled with this cortical parcellation and the subject's subcortical labels. A network's regions are fixed when it is built.">
          <Select aria-label="Tractography atlas" value={draftAtlas} onValueChange={setDraftAtlas} options={names.map((name) => ({ value: name, label: name }))} />
        </Field>
        <Field label="Seeds" help="Random seeds placed in white matter. More seeds take longer and give more streamlines per edge.">
          <NumberInput value={draftSeeds} min={1000} step={10000} onValueChange={(v) => setDraftSeeds(Math.max(1000, Math.round(v ?? 200_000)))} />
        </Field>
      </div>
    </Dialog>
  );
}
