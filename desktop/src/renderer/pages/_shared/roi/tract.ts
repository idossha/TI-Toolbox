/**
 * `/api/tract/*`: a subject's white-matter network as a target (`tit/server/routes/tract.py`).
 * Plain fetch for the binary route because a 202 is normal there, as for the scene payloads
 * (`pages/_shared/scene/api.ts`).
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useMemo } from "react";
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";
import { categoricalColor, rgbToHex } from "../../../scene/palette";
import { parseTvsl1 } from "../../../scene/tvsl";
import type { Rgb, SceneLines } from "../../../scene/types";
import type { TractConnection, TractPreset } from "./networkChoice";
import type { NetworkRoiValue } from "./types";

export type TractManifest = components["schemas"]["TractManifest"];
export type TractEdge = components["schemas"]["TractEdge"];
export type TractMask = components["schemas"]["TractMask"];
export type TractMaskRequest = components["schemas"]["TractMaskRequest"];
export type TractRanking = components["schemas"]["TractRanking"];
export type RegionPair = [string, string];

/** `tit/server/routes/tract.py::MAX_EDGES`. */
export const MAX_DRAWN_EDGES = 64;

export async function getTractManifest(subject: string): Promise<TractManifest> {
  return unwrap(await api.GET("/api/tract/manifest", { params: { query: { subject } } }), "/api/tract/manifest");
}

export async function getTractEdges(subject: string, seeds: string[]): Promise<TractEdge[]> {
  const body = unwrap(await api.GET("/api/tract/edges", { params: { query: { subject, seed: seeds } } }), "/api/tract/edges");
  return body.edges;
}

export async function createTractMask(body: TractMaskRequest): Promise<TractMask> {
  return unwrap(await api.POST("/api/tract/mask", { body }), "/api/tract/mask");
}

export async function getTractPresets(subject: string): Promise<TractPreset[]> {
  return unwrap(await api.GET("/api/tract/presets", { params: { query: { subject } } }), "/api/tract/presets").presets;
}

export async function getTractConnections(subject: string, simulation: string): Promise<TractConnection[]> {
  return unwrap(await api.GET("/api/tract/connections", { params: { query: { subject, simulation } } }), "/api/tract/connections").connections;
}

export async function getTractMasks(subject: string): Promise<TractMask[]> {
  return unwrap(await api.GET("/api/tract/masks", { params: { query: { subject } } }), "/api/tract/masks").masks;
}

export async function getTractRankings(subject: string, exRun: string): Promise<TractRanking[]> {
  return unwrap(await api.GET("/api/tract/rankings", { params: { query: { subject, ex_run: exRun } } }), "/api/tract/rankings").rankings;
}

/** `{building: true}` on a cold cache; the query polls. */
export async function getTractStreamlines(subject: string, pairs: RegionPair[]): Promise<ReturnType<typeof parseTvsl1> | { building: true }> {
  const query = new URLSearchParams({ subject });
  for (const [a, b] of pairs) query.append("pair", `${a}|${b}`);
  const response = await fetch(`/api/tract/streamlines?${query}`, { credentials: "same-origin" });
  if (response.status === 202) return { building: true };
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof error?.detail === "string" ? error.detail : `Could not load the streamlines (${response.status}).`);
  }
  return parseTvsl1(await response.arrayBuffer());
}

export function useTractManifest(subject: string | undefined): UseQueryResult<TractManifest> {
  return useQuery({
    queryKey: ["tract-manifest", subject],
    queryFn: () => getTractManifest(subject as string),
    enabled: !!subject,
  });
}

export function useTractEdges(subject: string | undefined, seeds: string[], fingerprint: string | null | undefined): UseQueryResult<TractEdge[]> {
  return useQuery({
    queryKey: ["tract-edges", subject, fingerprint, [...seeds].sort()],
    queryFn: () => getTractEdges(subject as string, seeds),
    enabled: !!subject && !!fingerprint && seeds.length > 0,
  });
}

export const samePair = (a: readonly string[], b: readonly string[]): boolean =>
  (a[0] === b[0] && a[1] === b[1]) || (a[0] === b[1] && a[1] === b[0]);

export const edgeKey = (edge: { region_a: string; region_b: string }): string => `${edge.region_a}|${edge.region_b}`;

/**
 * The rows the pane draws, in a stable order: a table row and its lines share a position, which is
 * what makes the swatch the line's colour. A selected edge is always drawn; the rest by streamline
 * count until the server's budget runs out.
 */
export function drawnEdges(edges: readonly TractEdge[], pairs: readonly RegionPair[], onlyPicked = false): TractEdge[] {
  const isPicked = (edge: TractEdge) => pairs.some((pair) => samePair(pair, [edge.region_a, edge.region_b]));
  const picked = edges.filter(isPicked);
  const rest = onlyPicked ? [] : edges.filter((edge) => !isPicked(edge));
  return [...picked, ...rest].slice(0, MAX_DRAWN_EDGES);
}

/** The row's colour by its position in the whole table, so selecting a row does not repaint it. */
export function edgeSwatch(edges: readonly TractEdge[], edge: TractEdge): Rgb {
  return categoricalColor(edges.indexOf(edge));
}

export const edgeSwatchHex = (edges: readonly TractEdge[], edge: TractEdge): string => rgbToHex(edgeSwatch(edges, edge));

/** Unselected lines stay in the scene at this fraction of their swatch, once something is selected. */
const UNSELECTED_DIM = 0.35;

/** The drawn edges' lines, or `null` until there is something to draw. Polls a cold cache. */
export function useTractLines(subject: string | undefined, value: NetworkRoiValue | null, fingerprint: string | null | undefined): {
  lines: SceneLines | null;
  drawn: TractEdge[];
  listed: number;
  building: boolean;
} {
  const edges = useTractEdges(subject, value?.seeds ?? [], fingerprint);
  const pairs = value?.pairs;
  // A preset, a region list or a top-N is already the choice: only by-connection offers the rest.
  const onlyPicked = !!value?.how && value.how !== "connection";
  const drawn = useMemo(() => drawnEdges(edges.data ?? [], pairs ?? [], onlyPicked), [edges.data, pairs, onlyPicked]);
  const wanted = useMemo(() => drawn.map((edge): RegionPair => [edge.region_a, edge.region_b]), [drawn]);
  const stream = useQuery({
    queryKey: ["tract-streamlines", subject, fingerprint, wanted],
    queryFn: () => getTractStreamlines(subject as string, wanted),
    enabled: !!subject && !!fingerprint && wanted.length > 0,
    refetchInterval: (query) => (query.state.data && "building" in query.state.data ? 1000 : false),
    staleTime: 5 * 60_000,
    placeholderData: (previous) => previous,
  });
  const lines = useMemo<SceneLines | null>(() => {
    const data = stream.data;
    if (!data || "building" in data || !data.groups || drawn.length === 0) return null;
    const colors = drawn.map((edge) => {
      const color = edgeSwatch(edges.data ?? [], edge);
      const dim = (pairs ?? []).length > 0 && !(pairs ?? []).some((pair) => samePair(pair, [edge.region_a, edge.region_b]));
      return dim ? (color.map((c) => c * UNSELECTED_DIM) as Rgb) : color;
    });
    // A held previous payload may name more groups than the new list has until the new one lands.
    if (data.groups.some((g) => g >= colors.length)) return null;
    return { positions: data.positions, offsets: data.offsets, groups: data.groups, colors };
  }, [stream.data, drawn, edges.data, pairs]);
  return { lines, drawn, listed: edges.data?.length ?? 0, building: !!stream.data && "building" in stream.data };
}
