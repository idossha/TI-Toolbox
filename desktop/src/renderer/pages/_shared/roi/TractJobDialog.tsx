/**
 * The Tractography step offered from a network target's empty state, the same `tract` job that
 * Pre-processing plans as its stage G7. The atlas is chosen here: a network's regions are fixed
 * when it is built.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../../ui/Button";
import { Callout } from "../../../ui/Feedback";
import { Field } from "../../../ui/Field";
import { Dialog } from "../../../ui/Overlay";
import { Select } from "../../../ui/Select";
import { Checkbox } from "../../../ui/Toggle";
import { notify } from "../../../ui/Toast";
import { submitJobGroup } from "../run/jobGroups";
import { getAtlases } from "./api";
import { getTractManifest } from "./tract";

/** `NetworkConfig.atlas`'s default. */
const DEFAULT_ATLAS = "DK40";

/**
 * Wire config of one subject's job. A subject with a tractogram only gets its network rebuilt
 * unless the user asks to track again, because tracking takes hours and the atlas does not need it.
 */
export function tractJobConfig(subject: string, atlas: string, retrack: boolean, hasTractogram: boolean) {
  const track = retrack || !hasTractogram;
  return {
    _type: "TractConfig",
    subject_id: subject,
    stages: track ? ["track", "network"] : ["network"],
    track: { overwrite: retrack && hasTractogram },
    network: { atlas },
  };
}

export function TractJobDialog({ open, onOpenChange, subjects }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  subjects: string[];
}) {
  const queryClient = useQueryClient();
  const [atlas, setAtlas] = useState(DEFAULT_ATLAS);
  const [retrack, setRetrack] = useState(false);
  const lead = subjects[0];
  const atlases = useQuery({
    queryKey: ["atlases", lead, "cortical", "subject"],
    queryFn: () => getAtlases(lead as string, "cortical", "subject"),
    enabled: open && !!lead,
  });
  const manifests = useQuery({
    queryKey: ["tract-manifests", subjects],
    queryFn: () => Promise.all(subjects.map((subject) => getTractManifest(subject))),
    enabled: open && subjects.length > 0,
  });
  const rows = manifests.data ?? [];
  const missingDwi = subjects.filter((_, i) => rows[i] && !rows[i]!.qsiprep_available && !rows[i]!.tractogram_available);
  const eligible = subjects.filter((subject) => !missingDwi.includes(subject));
  const existing = rows.filter((row) => row.tractogram_available || row.available).length;
  const submit = useMutation({
    mutationFn: () => {
      const configs = eligible.map((subject) => {
        const row = rows[subjects.indexOf(subject)];
        return { subject_id: subject, config: tractJobConfig(subject, atlas, retrack, !!row?.tractogram_available) };
      });
      return submitJobGroup("tract", configs[0]!.config, eligible, { subjectConfigs: configs, overwrite: existing > 0 });
    },
    onSuccess: () => {
      notify.success(`Queued tractography for ${eligible.length} subject(s).`);
      void queryClient.invalidateQueries({ queryKey: ["tract-manifest"] });
      onOpenChange(false);
    },
    onError: (error) => notify.error(error.message),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Tractography"
      description={subjects.join(", ")}
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" disabled={eligible.length === 0 || !manifests.data || submit.isPending} onClick={() => submit.mutate()} data-testid="tract-job-run">
            {submit.isPending ? "Queueing…" : "Run"}
          </Button>
        </>
      }
    >
      <div data-testid="tract-job-form" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", minWidth: 360 }}>
        <Field label="Atlas" help="Streamline ends are labelled with this cortical parcellation and the subject's subcortical labels. The network's regions are fixed when it is built.">
          <Select
            aria-label="Network atlas"
            value={atlas}
            onValueChange={setAtlas}
            options={(atlases.data ?? [{ id: DEFAULT_ATLAS, name: DEFAULT_ATLAS }]).map((a) => ({ value: a.id, label: a.name }))}
          />
        </Field>
        {existing > 0 && (
          <Checkbox checked={retrack} onCheckedChange={setRetrack} label="Track again (replaces the existing tractogram)" />
        )}
        {existing > 0 && !retrack && (
          <p className="field-help">An existing tractogram is kept; only its network is rebuilt.</p>
        )}
        {missingDwi.length > 0 && (
          <Callout kind="info">No QSIPrep output for {missingDwi.join(", ")}: run QSIPrep first. {eligible.length > 0 ? "The other subjects will run." : ""}</Callout>
        )}
        <p className="field-help">Replacing a network makes every mask built from it stale; each has to be created again.</p>
      </div>
    </Dialog>
  );
}
