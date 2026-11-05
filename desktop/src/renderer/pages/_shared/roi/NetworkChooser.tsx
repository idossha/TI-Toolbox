/**
 * Choosing a network, for every page that needs one: a preset, by region, by connection, or the
 * strongest connections of a simulation. All four write region-name pairs into one
 * `NetworkRoiValue`, which the 3D pane draws (`NetworkPane`) and a click there edits. No edge is
 * called strong or recommended: counts and medians are stated, and a top-N is ordered by the metric
 * the user names.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../../ui/Button";
import { Callout, Skeleton } from "../../../ui/Feedback";
import { Field, TextInput } from "../../../ui/Field";
import { NumberInput } from "../../../ui/NumberInput";
import { SegmentedControl } from "../../../ui/SegmentedControl";
import { Select } from "../../../ui/Select";
import { SelectionList, SelectionPicker, type SelectionItem } from "../../../ui/SelectionList";
import { Checkbox } from "../../../ui/Toggle";
import {
  autoNetworkName,
  CONNECTION_METRICS,
  HOW_LABELS,
  pairsFromTo,
  pairTotals,
  presetPairs,
  presetTotals,
  removedSentence,
  samePairSet,
  strongestPairs,
  withChoice,
  type TractConnection,
  type TractPreset,
} from "./networkChoice";
import { edgeKey, edgeSwatchHex, getTractConnections, getTractPresets, samePair, useTractEdges, useTractManifest, type RegionPair, type TractEdge } from "./tract";
import { TractJobDialog } from "./TractJobDialog";
import { NETWORK_NAME_RE, withNetworkEdit, type NetworkHow, type NetworkRoiValue, type RoiValue } from "./types";

const percent = (share: number): string => `${(share * 100).toFixed(share < 0.001 ? 2 : 1)} %`;
const count = (n: number): string => n.toLocaleString("en-US");
const DEFAULT_TOP_N = 10;
/** `tit.server.routes.tract.DEFAULT_MIN_N`. */
const DEFAULT_MIN_N = 5;

export function NetworkChooser({ value, onChange, subject, simulation, disabled, defaultHow = "connection", nameLabel, nameHelp, strongestEmpty, extra }: {
  value: NetworkRoiValue;
  onChange: (value: RoiValue) => void;
  subject: string | undefined;
  /** Offers "Strongest here", which reads this simulation's assessed edges. */
  simulation?: string;
  disabled?: boolean;
  defaultHow?: NetworkHow;
  nameLabel: string;
  nameHelp: string;
  /** What the Strongest tab offers while this simulation has no assessed edges. */
  strongestEmpty?: ReactNode;
  /** One more way in, beside the four (an existing bundle file). */
  extra?: { label: string; active: boolean; onSelect: () => void; content: ReactNode };
}) {
  const manifest = useTractManifest(subject);
  const fingerprint = manifest.data?.fingerprint;
  const how = value.how ?? defaultHow;
  const edges = useTractEdges(subject, value.seeds, fingerprint);
  const presets = useQuery({
    queryKey: ["tract-presets", subject, fingerprint],
    queryFn: () => getTractPresets(subject as string),
    enabled: !!fingerprint && how === "preset",
  });
  const connections = useQuery({
    queryKey: ["tract-connections", subject, simulation],
    queryFn: () => getTractConnections(subject as string, simulation as string),
    enabled: !!subject && !!simulation && how === "strongest",
    retry: false,
  });
  const [jobOpen, setJobOpen] = useState(false);

  const edit = (patch: Partial<NetworkRoiValue>) => onChange(withChoice(value, patch, withNetworkEdit));
  const list = useMemo(() => edges.data ?? [], [edges.data]);

  // By region and strongest are rules, not rows: the pairs follow the answer whenever it changes.
  const derived = useMemo<RegionPair[] | null>(() => {
    if (how === "region" && edges.data) return pairsFromTo(edges.data, value.seeds, value.to ?? [], value.minN);
    if (how === "strongest" && connections.data && value.metric) {
      return strongestPairs(connections.data, value.metric as keyof TractConnection, value.topN ?? DEFAULT_TOP_N, value.minN);
    }
    return null;
  }, [how, edges.data, connections.data, value.seeds, value.to, value.minN, value.metric, value.topN]);
  useEffect(() => {
    if (!derived || samePairSet(derived, value.pairs)) return;
    const patch: Partial<NetworkRoiValue> = { pairs: derived };
    // The pane lists edges by seed: a top-N's seeds are simply the regions it joins.
    if (how === "strongest") patch.seeds = [...new Set(derived.flat())];
    edit(patch);
    // `value` and `onChange` are fresh every render; the fact to react to is the derived list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [derived]);

  const regionItems = useMemo<SelectionItem[]>(
    () => (manifest.data?.regions ?? []).map((r) => ({ id: r.name, label: r.name, detail: r.cortical ? "cortical" : "subcortical", search: r.name })),
    [manifest.data],
  );
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
  const presetItems = useMemo<SelectionItem[]>(
    () =>
      (presets.data ?? []).map((preset) => ({
        id: preset.id,
        // The reason sits under the name: a column of its own is cut off in a narrow form.
        label: preset.reason ? (
          <>
            {preset.label}
            <span className="field-help" style={{ display: "block", whiteSpace: "normal" }}>{preset.reason}</span>
          </>
        ) : (
          preset.label
        ),
        search: `${preset.label} ${preset.id}`,
        value: preset,
        disabled: !!preset.reason,
        data: { state: preset.reason ? "unavailable" : "available" },
      })),
    [presets.data],
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
            ? "Run tractography to target its network."
            : "It needs QSIPrep output first (Pre-processing page, Diffusion)."}
        </Callout>
        <Button variant="secondary" size="sm" disabled={!canRun || disabled} onClick={() => setJobOpen(true)} data-testid="network-build">
          Run tractography…
        </Button>
        <TractJobDialog open={jobOpen} onOpenChange={setJobOpen} subjects={[subject]} />
      </div>
    );
  }

  const data = manifest.data;
  const chosenPreset = presets.data?.find((p) => p.id === value.preset);
  const totals =
    how === "preset"
      ? chosenPreset
        ? presetTotals(chosenPreset, !!value.includeOpposite)
        : { streamlines: 0, edges: 0 }
      : pairTotals(how === "strongest" ? (connections.data ?? []) : list, value.pairs);
  const nameValid = NETWORK_NAME_RE.test(value.name);
  const howOptions: { value: string; label: string }[] = (["preset", "region", "connection", ...(simulation ? (["strongest"] as const) : [])] as NetworkHow[]).map((option) => ({ value: option, label: HOW_LABELS[option] }));
  if (extra) howOptions.push({ value: "extra", label: extra.label });

  const setHow = (next: string) => {
    if (next === "extra") return extra?.onSelect();
    // Another way of choosing starts empty: what the last one chose is not what this one says.
    const fresh: Partial<NetworkRoiValue> = { how: next as NetworkHow, preset: undefined, seeds: [], to: [], pairs: [], metric: undefined };
    if (next === "strongest") fresh.topN = value.topN ?? DEFAULT_TOP_N;
    // A preset takes every edge of its set; anything else starts from the same floor as a target.
    if (value.how === "preset") fresh.minN = DEFAULT_MIN_N;
    if (extra?.active) extra.onSelect();
    edit(fresh);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }} data-testid="network-chooser" data-how={extra?.active ? "extra" : how}>
      <p className="field-help" data-testid="network-summary">
        {data.atlas} network · {count(data.n_streamlines ?? 0)} streamlines · {count(data.n_edges ?? 0)} edges
        {" "}· {((data.frac_both_ends_assigned ?? 0) * 100).toFixed(1)} % with both ends labelled
        {data.qc_passed === false ? " · the frame check failed" : ""}
      </p>
      <SegmentedControl aria-label="Choose the network" value={extra?.active ? "extra" : how} onValueChange={setHow} options={howOptions} disabled={disabled} />

      {extra?.active ? (
        extra.content
      ) : (
        <>
          {how === "preset" && (
            <Field label="Region set" help="A set of atlas regions, not an anatomical claim. What it holds depends on the tractography.">
              <SelectionList
                items={presetItems}
                value={value.preset ? [value.preset] : []}
                mode="single"
                onChange={(keys) => {
                  const preset = presets.data?.find((p) => p.id === keys[0]);
                  if (!preset) return;
                  // One streamline is an edge of this set: minN would otherwise hide it from the mask.
                  edit({ preset: preset.id, presetSameSide: preset.same_side, seeds: preset.seeds, pairs: presetPairs(preset, !!value.includeOpposite), minN: 1 });
                }}
                toggleOnRowClick
                label="Region sets"
                headers={{ label: "Region set" }}
                columns={[
                  { id: "n", header: "Streamlines", numeric: true, cell: (item) => count(presetTotals(item.value as TractPreset, !!value.includeOpposite).streamlines) },
                  { id: "edges", header: "Edges", numeric: true, cell: (item) => count(presetTotals(item.value as TractPreset, !!value.includeOpposite).edges) },
                ]}
                idPrefix="network-preset"
                testId="network-presets"
                hideBulk
                hideBadge
                hideFilter
                loading={presets.isPending}
                emptyMessage="No region set for this network."
                maxHeight={260}
              />
              {presets.error && <Callout kind="danger">{presets.error.message}</Callout>}
              <Checkbox
                checked={!!value.includeOpposite}
                disabled={disabled}
                onCheckedChange={(includeOpposite) => edit({ includeOpposite, ...(chosenPreset ? { pairs: presetPairs(chosenPreset, includeOpposite) } : {}) })}
                label="Include opposite-hemisphere connections"
              />
              <p className="field-help">Thalamocortical sets only. They keep same-hemisphere edges by default, by atlas label; the others are never filtered.</p>
            </Field>
          )}

          {(how === "region" || how === "connection") && (
            <Field
              label={how === "region" ? "From" : "Seed regions"}
              required
              help={how === "region" ? "One region is enough: without a To, every edge it has." : "Every edge touching a seed is listed below. Click cortical regions in the 3D pane, or choose any region here."}
            >
              <SelectionPicker
                items={regionItems}
                value={value.seeds}
                onChange={(seeds) => edit({ seeds, pairs: value.pairs.filter((p) => seeds.some((s) => p.includes(s))) })}
                label="Regions"
                title={how === "region" ? "Choose the From regions" : "Choose seed regions"}
                headers={{ label: "Region", detail: "Kind" }}
                filterPlaceholder="Filter regions…"
                idPrefix="network-seed"
                placeholder={how === "region" ? "Add a region…" : "Add seed…"}
                triggerTestId="network-seeds"
                disabled={disabled}
              />
            </Field>
          )}

          {how === "region" && (
            <Field label="To" help="Empty means every region the From regions reach.">
              <SelectionPicker
                items={regionItems}
                value={value.to ?? []}
                onChange={(to) => edit({ to })}
                label="Regions"
                title="Choose the To regions"
                headers={{ label: "Region", detail: "Kind" }}
                filterPlaceholder="Filter regions…"
                idPrefix="network-to"
                placeholder="Every region reached"
                triggerTestId="network-to"
                disabled={disabled}
              />
            </Field>
          )}

          {how === "connection" && value.seeds.length > 0 && (
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
                    edit({ pairs });
                  }}
                  toggleOnRowClick
                  label="Edges"
                  headers={{ label: "Region A – Region B" }}
                  columns={[
                    { id: "n", header: "n", numeric: true, cell: (item) => count((item.value as TractEdge).n) },
                    { id: "share", header: "share", numeric: true, cell: (item) => percent((item.value as TractEdge).share) },
                  ]}
                  filterPlaceholder="Filter edges…"
                  idPrefix="network-edge"
                  testId="network-edges"
                  loading={edges.isPending}
                  emptyMessage="No streamline ends in these regions."
                  maxHeight={220}
                />
              )}
            </Field>
          )}

          {how === "strongest" && (
            connections.error ? (
              <div data-testid="network-strongest-empty" style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                <Callout kind="info">{connections.error.message}</Callout>
                {strongestEmpty}
              </div>
            ) : (
              <div className="form-grid">
                <Field label="Ordered by" required help="Whichever you name. None is suggested, and none means more than the others do." htmlFor="network-metric">
                  <Select id="network-metric" value={value.metric} onValueChange={(metric) => edit({ metric })} options={CONNECTION_METRICS.map((m) => ({ value: String(m.value), label: m.label }))} placeholder="Choose a metric" disabled={disabled} />
                </Field>
                <Field label="Connections" help="How many, from the top of that order.">
                  <NumberInput value={value.topN ?? DEFAULT_TOP_N} min={1} step={1} disabled={disabled} onValueChange={(v) => edit({ topN: Math.max(1, Math.round(v ?? DEFAULT_TOP_N)) })} />
                </Field>
              </div>
            )
          )}

          {how !== "preset" && (
            <Field label="Minimum streamlines per edge" help="An edge with fewer streamlines cannot be chosen.">
              <NumberInput value={value.minN} min={1} step={1} disabled={disabled}
                onValueChange={(v) => {
                  const minN = Math.max(1, Math.round(v ?? 1));
                  const keep = value.pairs.filter((p) => { const e = list.find((row) => samePair(p, [row.region_a, row.region_b])); return !e || e.n >= minN; });
                  edit({ minN, pairs: keep });
                }} />
            </Field>
          )}

          <p className="field-help tabular" data-testid="network-count" data-streamlines={totals.streamlines}>
            {value.pairs.length === 0 ? "Nothing chosen yet." : `${count(totals.streamlines)} streamlines · ${count(totals.edges)} edge${totals.edges === 1 ? "" : "s"}`}
            {how === "preset" && chosenPreset?.same_side && !value.includeOpposite && value.pairs.length > 0 && <span data-testid="network-removed"> · {removedSentence(chosenPreset)}</span>}
          </p>

          <Field label={nameLabel} required help={nameHelp} htmlFor="network-mask-name">
            <TextInput id="network-mask-name" data-testid="network-mask-name" value={value.name} disabled={disabled} placeholder="e.g. thalamocortical_lh"
              onChange={(e) => {
                const typed = e.target.value;
                // Clearing the field hands the name back to the choice.
                onChange(withNetworkEdit(value, typed === "" ? { name: autoNetworkName(value), nameEdited: false } : { name: typed, nameEdited: true }));
              }} />
          </Field>
          {value.name !== "" && !nameValid && <p className="field-help" role="alert">Use letters, digits, _ and - only.</p>}
        </>
      )}
    </div>
  );
}
