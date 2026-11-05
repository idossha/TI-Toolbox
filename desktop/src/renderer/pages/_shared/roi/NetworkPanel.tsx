/**
 * The `network` target: choose a network (`NetworkChooser`), then write its mask.
 *
 * The value (`NetworkRoiValue`) is the row's state; the 3D pane and this panel both edit it through
 * `withNetworkEdit`, so editing the selection in either marks the mask stale. No edge is called
 * strong or recommended: rows are sorted by streamline count and the count is stated.
 */
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../../ui/Button";
import { Callout } from "../../../ui/Feedback";
import { Field } from "../../../ui/Field";
import { NumberInput } from "../../../ui/NumberInput";
import { AlertDialog } from "../../../ui/Overlay";
import { NetworkChooser } from "./NetworkChooser";
import { createTractMask, samePair, useTractEdges, useTractManifest } from "./tract";
import { NETWORK_NAME_RE, withNetworkEdit, type NetworkRoiValue, type RoiValue } from "./types";

export function NetworkPanel({ value, onChange, subject, disabled }: {
  value: NetworkRoiValue;
  onChange: (value: RoiValue) => void;
  subject: string | undefined;
  disabled?: boolean;
}) {
  const queryClient = useQueryClient();
  const manifest = useTractManifest(subject);
  const fingerprint = manifest.data?.fingerprint;
  const edges = useTractEdges(subject, value.seeds, fingerprint);
  const [confirmReplace, setConfirmReplace] = useState(false);

  // The network was rebuilt under this row: its mask no longer describes it. Preflight would refuse.
  const rebuilt = !!value.mask && !!fingerprint && value.mask.fingerprint !== fingerprint;
  useEffect(() => {
    if (rebuilt) onChange(withNetworkEdit(value, {}));
    // `value` and `onChange` are fresh every render; the fact to react to is this boolean.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rebuilt]);

  const create = useMutation({
    mutationFn: (overwrite: boolean) =>
      createTractMask({ subject: subject as string, name: value.name, pairs: value.pairs, min_count: value.minCount, min_n: value.minN, overwrite }),
    onSuccess: (mask) => {
      onChange({
        ...value,
        stale: false,
        mask: { path: mask.path, fingerprint: mask.fingerprint, nEdges: mask.n_edges, nStreamlines: mask.n_streamlines, nVoxels: mask.n_voxels, volumeMm3: mask.volume_mm3 },
      });
      void queryClient.invalidateQueries({ queryKey: ["atlases", subject] });
    },
    onError: (error: Error & { status?: number }) => {
      if (error.status === 409) setConfirmReplace(true);
    },
  });

  const list = edges.data ?? [];
  const nameValid = NETWORK_NAME_RE.test(value.name);
  const belowMin = list.filter((edge) => value.pairs.some((p) => samePair(p, [edge.region_a, edge.region_b])) && edge.n < value.minN);
  const canCreate = value.pairs.length > 0 && nameValid && belowMin.length === 0 && !create.isPending && !disabled;
  const state = value.mask ? "S4" : value.pairs.length > 0 ? "S3" : value.seeds.length > 0 ? "S2" : "S1";
  const chooser = (
    <NetworkChooser
      value={value}
      onChange={onChange}
      subject={subject}
      disabled={disabled}
      nameLabel="Mask name"
      nameHelp="Letters, digits, _ and -. Written as masks/tract-<name>.nii.gz in this subject's head model."
    />
  );
  // S0 is the chooser's: no network, nothing to write a mask from.
  if (!manifest.data?.available) return chooser;

  return (
    <div className="roi-network" data-testid="network-panel" data-state={state} style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {chooser}
      <Field label="Voxel density threshold" help="Voxels crossed by at least this many of the chosen streamlines are in the mask.">
        <NumberInput value={value.minCount} min={1} step={1} disabled={disabled}
          onValueChange={(v) => onChange(withNetworkEdit(value, { minCount: Math.max(1, Math.round(v ?? 1)) }))} />
      </Field>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <Button variant="primary" size="sm" disabled={!canCreate} onClick={() => create.mutate(false)} data-testid="network-create-mask">
          {create.isPending ? "Creating mask…" : value.stale ? "Create the mask again" : "Create mask"}
        </Button>
        {value.mask && (
          <span className="field-help tabular" data-testid="network-mask-result">
            {value.mask.nEdges} edge{value.mask.nEdges === 1 ? "" : "s"} · {value.mask.nStreamlines.toLocaleString("en-US")} streamlines · {Math.round(value.mask.volumeMm3).toLocaleString("en-US")} mm³
          </span>
        )}
        {value.stale && !value.mask && <span className="field-help" data-testid="network-mask-stale">The selection changed. Create the mask again to run.</span>}
      </div>
      {create.error && (create.error as { status?: number }).status !== 409 && <Callout kind="danger">{create.error.message}</Callout>}
      <p className="field-help">The optimizer evaluates this mask on white matter, in this subject&rsquo;s space.</p>
      <AlertDialog
        open={confirmReplace}
        onOpenChange={setConfirmReplace}
        title="Replace mask"
        description={`A mask named "${value.name}" already exists for sub-${subject}. Replace it?`}
        confirmLabel="Replace mask"
        onConfirm={() => {
          setConfirmReplace(false);
          create.mutate(true);
        }}
      />
    </div>
  );
}
