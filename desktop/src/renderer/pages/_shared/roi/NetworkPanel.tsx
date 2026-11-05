/**
 * The `network` target: choose seed regions, then the edges they make, then write a mask.
 *
 * The value (`NetworkRoiValue`) is the row's state; the 3D pane and this panel both edit it through
 * `withNetworkEdit`, so editing the selection in either marks the mask stale. No edge is called
 * strong or recommended: rows are sorted by streamline count and the count is stated.
 */
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../../ui/Button";
import { Callout, Skeleton } from "../../../ui/Feedback";
import { Field, TextInput } from "../../../ui/Field";
import { NumberInput } from "../../../ui/NumberInput";
import { SelectionList, SelectionPicker, type SelectionItem } from "../../../ui/SelectionList";
import { AlertDialog } from "../../../ui/Overlay";
import { createTractMask, edgeKey, edgeSwatchHex, samePair, useTractEdges, useTractManifest, type RegionPair, type TractEdge } from "./tract";
import { TractJobDialog } from "./TractJobDialog";
import { NETWORK_NAME_RE, withNetworkEdit, type NetworkRoiValue, type RoiValue } from "./types";

const percent = (share: number): string => `${(share * 100).toFixed(share < 0.001 ? 2 : 1)} %`;

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
  const [jobOpen, setJobOpen] = useState(false);
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

  const regionItems = useMemo<SelectionItem[]>(
    () => (manifest.data?.regions ?? []).map((r) => ({ id: r.name, label: r.name, detail: r.cortical ? "cortical" : "subcortical", search: r.name })),
    [manifest.data],
  );
  const list = edges.data ?? [];
  const edgeItems = useMemo<SelectionItem[]>(
    () =>
      list.map((edge) => ({
        id: edgeKey(edge),
        label: `${edge.region_a} – ${edge.region_b}`,
        search: `${edge.region_a} ${edge.region_b}`,
        swatch: edgeSwatchHex(list, edge),
        value: edge,
        disabled: edge.n < value.minN,
        reason: edge.n < value.minN ? `Fewer than ${value.minN} streamlines` : undefined,
      })),
    [list, value.minN],
  );
  const selectedKeys = useMemo(
    () => list.filter((edge) => value.pairs.some((p) => samePair(p, [edge.region_a, edge.region_b]))).map(edgeKey),
    [list, value.pairs],
  );

  if (!subject) return <p className="field-help">Choose a subject first.</p>;
  if (manifest.isPending) return <Skeleton height={64} />;
  if (manifest.error) return <Callout kind="danger">{manifest.error.message}</Callout>;

  // S0: no network yet.
  if (!manifest.data?.available) {
    const canRun = manifest.data?.qsiprep_available || manifest.data?.tractogram_available;
    return (
      <div className="roi-network" data-testid="network-unavailable" data-state="S0">
        <Callout kind="info">
          No tractography for sub-{subject}.{" "}
          {canRun
            ? "Build its white-matter network to target one."
            : "It needs QSIPrep output first (Pre-processing page, DWI)."}
        </Callout>
        <Button variant="secondary" size="sm" disabled={!canRun || disabled} onClick={() => setJobOpen(true)} data-testid="network-build">
          Build network…
        </Button>
        <TractJobDialog open={jobOpen} onOpenChange={setJobOpen} subjects={[subject]} />
      </div>
    );
  }

  const data = manifest.data;
  const nameValid = NETWORK_NAME_RE.test(value.name);
  const belowMin = list.filter((edge) => value.pairs.some((p) => samePair(p, [edge.region_a, edge.region_b])) && edge.n < value.minN);
  const canCreate = value.pairs.length > 0 && nameValid && belowMin.length === 0 && !create.isPending && !disabled;
  const state = value.mask ? "S4" : value.pairs.length > 0 ? "S3" : value.seeds.length > 0 ? "S2" : "S1";

  return (
    <div className="roi-network" data-testid="network-panel" data-state={state} style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <p className="field-help" data-testid="network-summary">
        {data.atlas} network · {(data.n_streamlines ?? 0).toLocaleString("en-US")} streamlines · {(data.n_edges ?? 0).toLocaleString("en-US")} edges
        {" "}· {((data.frac_both_ends_assigned ?? 0) * 100).toFixed(1)} % with both ends labelled
        {data.qc_passed === false ? " · the frame check failed" : ""}
      </p>
      <Field label="Seed regions" required help="Every edge touching a seed is listed below. Click cortical regions in the 3D pane, or choose any region here.">
        <SelectionPicker
          items={regionItems}
          value={value.seeds}
          onChange={(seeds) => onChange(withNetworkEdit(value, { seeds, pairs: value.pairs.filter((p) => seeds.some((s) => p.includes(s))) }))}
          label="Regions"
          title="Choose seed regions"
          headers={{ label: "Region", detail: "Kind" }}
          filterPlaceholder="Filter regions…"
          idPrefix="network-seed"
          placeholder="Add seed…"
          triggerTestId="network-seeds"
          disabled={disabled}
        />
      </Field>
      {value.seeds.length > 0 && (
        <Field label="Edges" required help="n is the streamlines between the two regions, share their fraction of all labelled streamlines. These counts depend on the tractography and are not connection strengths.">
          {edges.error ? (
            <Callout kind="danger">{edges.error.message}</Callout>
          ) : (
            <SelectionList
              items={edgeItems}
              value={selectedKeys}
              onChange={(keys) => {
                const byKey = new Map(list.map((edge) => [edgeKey(edge), edge] as const));
                const pairs = keys.map((key) => byKey.get(key)).filter((e): e is TractEdge => !!e).map((e): RegionPair => [e.region_a, e.region_b]);
                onChange(withNetworkEdit(value, { pairs }));
              }}
              toggleOnRowClick
              label="Edges"
              headers={{ label: "Region A – Region B" }}
              columns={[
                { id: "n", header: "n", numeric: true, cell: (item) => (item.value as TractEdge).n.toLocaleString("en-US") },
                { id: "share", header: "share", numeric: true, cell: (item) => percent((item.value as TractEdge).share) },
              ]}
              filterPlaceholder="Filter edges…"
              idPrefix="network-edge"
              testId="network-edges"
              loading={edges.isPending}
              emptyMessage="No streamline ends in these regions."
              maxHeight={220}
              aria="grid"
            />
          )}
        </Field>
      )}
      <div className="form-grid">
        <Field label="Minimum streamlines per edge" help="An edge with fewer streamlines stays listed, and cannot be chosen.">
          <NumberInput value={value.minN} min={1} step={1} disabled={disabled}
            onValueChange={(v) => {
              const minN = Math.max(1, Math.round(v ?? 1));
              const keep = value.pairs.filter((p) => { const e = list.find((row) => samePair(p, [row.region_a, row.region_b])); return !e || e.n >= minN; });
              onChange(withNetworkEdit(value, { minN, pairs: keep }));
            }} />
        </Field>
        <Field label="Voxel density threshold" help="Voxels crossed by at least this many of the chosen streamlines are in the mask.">
          <NumberInput value={value.minCount} min={1} step={1} disabled={disabled}
            onValueChange={(v) => onChange(withNetworkEdit(value, { minCount: Math.max(1, Math.round(v ?? 1)) }))} />
        </Field>
        <Field label="Mask name" required help="Letters, digits, _ and -. Written as masks/tract-<name>.nii.gz in this subject's head model." htmlFor="network-mask-name">
          <TextInput id="network-mask-name" data-testid="network-mask-name" value={value.name} disabled={disabled} placeholder="e.g. thalamocortical_lh"
            onChange={(e) => onChange(withNetworkEdit(value, { name: e.target.value }))} />
        </Field>
      </div>
      {value.name !== "" && !nameValid && <p className="field-help" role="alert">Use letters, digits, _ and - only.</p>}
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
