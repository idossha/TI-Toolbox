/**
 * React Query wiring for the scene routes. One hook per pane so the three pages share the cache:
 * opening the Simulator and then the Optimizer for the same subject re-uses the manifest, the
 * atlas legend and the electrode net rather than re-requesting them.
 *
 * Surface and label payloads are `TVSC1` binaries fetched and decoded here, then handed to
 * `renderer/scene/` as typed arrays. The guide's are immutable, so they are cached for ever.
 */
import { useQueries, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useMemo } from "react";
import {
  getGuideTvsc,
  guideLabelsUrl,
  guideSurfaceUrl,
  type Tvsc1,
  getGuideElectrodes,
  getGuideManifest,
  getGuideRegions,
  getSceneElectrodes,
  getSceneManifest,
  getSceneRegions,
  labelsUrl,
  surfaceUrl,
  type SceneElectrodes,
  type SceneManifest,
  type SceneRegions,
  type GuideElectrodes,
  type GuideManifest,
  type GuideRegions,
} from "./api";

/** `Retry-After` on a scene 202 is one second (`tit/server/routes/scene.py::RETRY_AFTER_S`). */
const POLL_MS = 1000;

/**
 * A build failure is reported once as a 500 and then cleared by the server. Retrying that HTTP
 * error starts another build and hides the failure behind a fresh 202 forever. HTTP failures
 * therefore require an explicit retry; only transport failures get bounded automatic retries.
 */
function retryScene(failureCount: number, error: Error): boolean {
  const status = (error as { status?: number } | null)?.status;
  if (status !== undefined) return false;
  return failureCount < 3;
}

export function useSceneManifest(subject: string | null): UseQueryResult<SceneManifest> {
  return useQuery({
    queryKey: ["scene", "manifest", subject],
    queryFn: () => getSceneManifest(subject as string),
    enabled: !!subject,
    retry: retryScene,
    refetchInterval: (query) => (query.state.status !== "error" && query.state.data?.building ? POLL_MS : false),
    staleTime: 5 * 60_000,
  });
}

export function useSceneElectrodes(subject: string | null, net: string | null): UseQueryResult<SceneElectrodes> {
  return useQuery({
    queryKey: ["scene", "electrodes", subject, net],
    queryFn: () => getSceneElectrodes(subject as string, net as string),
    enabled: !!subject && !!net,
    retry: retryScene,
    staleTime: 5 * 60_000,
  });
}

export function useSceneRegions(subject: string | null, atlas: string | null): UseQueryResult<SceneRegions> {
  return useQuery({
    queryKey: ["scene", "regions", subject, atlas],
    queryFn: () => getSceneRegions(subject as string, atlas as string),
    enabled: !!subject && !!atlas,
    retry: retryScene,
    refetchInterval: (query) => (query.state.status !== "error" && query.state.data?.building ? POLL_MS : false),
    staleTime: 5 * 60_000,
  });
}

/**
 * Both surfaces of one **subject**, decoded — the subject counterpart of `useGuideSurfaces`.
 *
 * Why the Simulator wants this and R4's guide-only rule still stands elsewhere: a free-hand
 * placement is a coordinate *in the subject's own head mesh* (`m2m_<id>/stim_configs/*.json`, the
 * format `tit/gui/extensions/electrode_placement.py` wrote and `tit/catalog.py::_read_freehand_file`
 * reads). A millimetre picked off the packaged guide is a millimetre in a different head, and
 * nothing downstream can detect the substitution — which is exactly why `<ScenePane>` refuses to
 * emit a coordinate while it is drawing the guide. Drawing the subject is what makes the gesture
 * *possible*, so the pane may only place electrodes when these hooks are the ones feeding it.
 *
 * Unlike the guide's, these bytes are not immutable — a re-run of `charm` changes them — so they
 * carry a finite `staleTime` rather than `Infinity`.
 */
const SUBJECT_SURFACE_QUERY = { staleTime: 30 * 60_000, gcTime: 60 * 60_000, retry: retryScene } as const;

export function useSceneSurfaces(subject: string | null, parts: { id: string; url: string }[]): UseQueryResult<Tvsc1 | null>[] {
  return useQueries({
    queries: parts.map((part) => ({
      queryKey: ["scene", "surface", subject, part.id],
      queryFn: () => getGuideTvsc(part.url),
      enabled: !!subject,
      ...SUBJECT_SURFACE_QUERY,
    })),
  });
}

/** `parts[]` of a SUBJECT manifest reduced to what `useSceneSurfaces` needs, memoised for the same
 *  reason `useGuideSurfaceRequests` is: a fresh array every render re-keys every surface query. */
export function useSceneSurfaceRequests(subject: string | null, manifest: SceneManifest | undefined): { id: string; url: string }[] {
  return useMemo(
    () => (!subject || !manifest ? [] : (manifest.parts ?? []).map((part) => ({ id: String(part.id), url: surfaceUrl(subject, String(part.id)) }))),
    [subject, manifest],
  );
}

/** The subject's per-vertex atlas labels aligned to its `gm`, as TVSC1. */
export function useSceneLabels(subject: string | null, atlas: string | null, ready: boolean): UseQueryResult<Tvsc1 | null> {
  return useQuery({
    queryKey: ["scene", "labels", subject, atlas],
    queryFn: () => getGuideTvsc(labelsUrl(subject as string, atlas as string)),
    enabled: !!subject && !!atlas && ready,
    ...SUBJECT_SURFACE_QUERY,
  });
}

// ------------------------------------------------------------------------------------- the guide

/**
 * The guide hooks. **None of them takes a subject**, and that is the whole point of R4: the query
 * keys below contain no subject id, so changing the selected research subjects cannot invalidate
 * them, cannot refetch them, and cannot remount what they feed.
 *
 * `staleTime: Infinity` and `gcTime: Infinity` because the payloads are immutable for the life of
 * the installation — the server serves them with `Cache-Control: immutable` for the same reason.
 * A refetch would re-fetch bytes that cannot have changed.
 */
const GUIDE_QUERY = { staleTime: Infinity, gcTime: Infinity, retry: retryScene } as const;

export function useGuideManifest(): UseQueryResult<GuideManifest> {
  return useQuery({ queryKey: ["guide", "manifest"], queryFn: getGuideManifest, ...GUIDE_QUERY });
}

export function useGuideElectrodes(net: string | null): UseQueryResult<GuideElectrodes> {
  return useQuery({
    queryKey: ["guide", "electrodes", net],
    queryFn: () => getGuideElectrodes(net as string),
    enabled: !!net,
    ...GUIDE_QUERY,
  });
}

export function useGuideRegions(atlas: string | null): UseQueryResult<GuideRegions> {
  return useQuery({
    queryKey: ["guide", "regions", atlas],
    queryFn: () => getGuideRegions(atlas as string),
    enabled: !!atlas,
    ...GUIDE_QUERY,
  });
}

/**
 * Both guide surfaces, in the manifest's own order, decoded.
 *
 * The URLs come from `parts[].url` when the manifest carries one, so adding a part is a server
 * change rather than a renderer change. `staleTime`/`gcTime` are `Infinity`: these bytes ship with
 * the installation and are served `Cache-Control: immutable`, so a refetch could only re-fetch
 * what cannot have changed — and re-uploading 145 k triangles is not free.
 */
export function useGuideSurfaces(parts: { id: string; url: string }[]): UseQueryResult<Tvsc1 | null>[] {
  return useQueries({
    queries: parts.map((part) => ({
      queryKey: ["guide", "surface", part.id],
      queryFn: () => getGuideTvsc(part.url),
      ...GUIDE_QUERY,
    })),
  });
}

/** The per-vertex atlas labels aligned to `gm`, as TVSC1. Enabled only once the legend is in hand:
 *  labels with no legend can highlight a region the pane cannot name. */
export function useGuideLabels(atlas: string | null, ready: boolean): UseQueryResult<Tvsc1 | null> {
  return useQuery({
    queryKey: ["guide", "labels", atlas],
    queryFn: () => getGuideTvsc(guideLabelsUrl(atlas as string)),
    enabled: !!atlas && ready,
    ...GUIDE_QUERY,
  });
}

/** `parts[]` reduced to what `useGuideSurfaces` needs, memoised so the query list is stable —
 *  a fresh array every render would re-key every surface query on every render. */
export function useGuideSurfaceRequests(manifest: GuideManifest | undefined): { id: string; url: string }[] {
  return useMemo(
    () =>
      (manifest?.parts ?? []).map((part) => ({
        id: String(part.id),
        // The packaged manifest's `url` has no `format`, and TVSC1 is what this renderer reads.
        url: guideSurfaceUrl(String(part.id)),
      })),
    [manifest],
  );
}
