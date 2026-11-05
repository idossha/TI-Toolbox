/**
 * The 3D pane of a `network` target: the subject's grey matter in the network's own atlas, where a
 * click on a cortical region adds a seed, and the listed edges' streamlines over it, where a click
 * on a line toggles that edge. The pane holds nothing: `value` is the row's, and every edit goes
 * back through `withNetworkEdit` exactly as the form's do.
 */
import { useCallback, useMemo, type ReactNode } from "react";
import { useTractLines, useTractManifest, samePair, type RegionPair } from "../roi/tract";
import { withNetworkEdit, type NetworkRoiValue, type RoiValue } from "../roi/types";
import { ScenePane } from "./ScenePane";
import { useSceneRegions } from "./queries";
import type { SceneRegionRef } from "./model";

const regionName = (region: { name: string; hemi?: string | null }): string => (region.hemi ? `${region.hemi}.${region.name}` : region.name);

export function NetworkPane({ subject, value, onChange, openMask }: {
  subject: string | undefined;
  value: NetworkRoiValue;
  onChange?: (value: RoiValue) => void;
  openMask?: ReactNode;
}) {
  const manifest = useTractManifest(subject);
  const atlas = manifest.data?.atlas ?? null;
  const known = useMemo(() => new Set((manifest.data?.regions ?? []).map((r) => r.name)), [manifest.data]);
  const legend = useSceneRegions(subject ?? null, atlas);
  const { lines, drawn, listed, building } = useTractLines(subject, value, manifest.data?.fingerprint);

  // The pane speaks atlas rows ({id, name, hemi}); the target speaks the network's region names.
  // Subcortical seeds have no row on this surface, so they stay in the form and survive a pick.
  const regions = useMemo<SceneRegionRef[]>(
    () =>
      (legend.data?.legend ?? []).flatMap((row) =>
        value.seeds.includes(regionName({ name: row.name, hemi: row.hemi })) ? [{ id: row.id, name: row.name, hemi: (row.hemi ?? undefined) as "lh" | "rh" | undefined }] : [],
      ),
    [legend.data, value.seeds],
  );
  const onRegionsChange = useCallback(
    (next: SceneRegionRef[]) => {
      const onSurface = new Set((legend.data?.legend ?? []).map((row) => regionName({ name: row.name, hemi: row.hemi })));
      const kept = value.seeds.filter((seed) => !onSurface.has(seed));
      // A region this network has no streamline ends in cannot be a seed.
      const seeds = [...kept, ...next.map(regionName).filter((name) => known.has(name))];
      onChange?.(withNetworkEdit(value, { seeds, pairs: value.pairs.filter((pair) => seeds.some((seed) => pair.includes(seed))) }));
    },
    [legend.data, value, known, onChange],
  );
  const onLinePick = useCallback(
    (group: number) => {
      const edge = drawn[group];
      if (!edge || edge.n < value.minN) return;
      const pair: RegionPair = [edge.region_a, edge.region_b];
      const on = value.pairs.some((p) => samePair(p, pair));
      onChange?.(withNetworkEdit(value, { pairs: on ? value.pairs.filter((p) => !samePair(p, pair)) : [...value.pairs, pair] }));
    },
    [drawn, value, onChange],
  );
  const lineLabel = useCallback(
    (group: number) => {
      const edge = drawn[group];
      return edge ? `${edge.region_a} – ${edge.region_b} · n ${edge.n}` : null;
    },
    [drawn],
  );

  const onlyPicked = !!value.how && value.how !== "connection";
  const note = !manifest.data?.available
    ? "No network yet: this subject's head is shown for orientation."
    : building
      ? "Preparing this network's streamlines…"
      : onlyPicked && value.pairs.length > 0
        ? `Showing ${drawn.length} of this network's ${value.pairs.length} edges, up to 100 streamlines each. The render draws them all.`
      : listed > drawn.length
        ? `Showing the ${drawn.length} largest of ${listed} edges. A selected edge is always shown.`
        : lines
          ? "Click a region to add or remove a seed, or a line to select or clear its edge."
          : "Click a region to add or remove a seed.";

  return (
    <div className="scene-pane-wrap" data-testid="scene-pane-wrap" data-target="network">
      <ScenePane
        mode="target"
        subject={subject}
        atlas={atlas}
        atlasLocked={!!atlas}
        regions={regions}
        onRegionsChange={onChange ? onRegionsChange : undefined}
        lines={lines}
        onLinePick={onChange ? onLinePick : undefined}
        lineLabel={lineLabel}
        note={note}
        toolbarLead={openMask}
      />
    </div>
  );
}
