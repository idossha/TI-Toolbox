// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SceneError, type SceneManifest, type SceneRegions } from "../../src/renderer/pages/_shared/scene/api";
import { useSceneManifest, useSceneRegions } from "../../src/renderer/pages/_shared/scene/queries";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const MANIFEST: Omit<SceneManifest, "building"> = {
  subject: "ernie", space: "subject-ras", cache: { state: "ready", built_ms: 12 },
  parts: [], bbox: [-5, -5, -5, 5, 5, 5], focus_bbox: [-5, -5, -5, 5, 5, 5],
  atlases: [], nets: [], volumes: [],
};
const REGIONS: Omit<SceneRegions, "building"> = {
  subject: "ernie", atlas: "DK40", cache: { state: "ready", built_ms: 12 },
  url: "/api/scene/labels?subject=ernie&atlas=DK40", legend: [],
};

const CASES = [
  { name: "manifest", useScene: () => useSceneManifest("ernie"), body: MANIFEST, path: "/api/scene/manifest?subject=ernie" },
  { name: "regions", useScene: () => useSceneRegions("ernie", "DK40"), body: REGIONS, path: "/api/scene/regions?subject=ernie&atlas=DK40" },
] as const;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

for (const { name, useScene, body, path } of CASES) {
  describe(`scene ${name} query`, () => {
    let container: HTMLDivElement;
    let root: Root;
    let client: QueryClient;
    let query: ReturnType<typeof useScene>;
    const fetcher = vi.fn<typeof fetch>();

    beforeEach(() => {
      vi.useFakeTimers();
      focusManager.setFocused(true);
      fetcher.mockReset();
      vi.stubGlobal("fetch", fetcher);
      client = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } });
      container = document.createElement("div");
      document.body.appendChild(container);
      root = createRoot(container);
    });
    afterEach(() => {
      act(() => root.unmount());
      client.clear();
      container.remove();
      focusManager.setFocused(undefined);
      vi.unstubAllGlobals();
      vi.useRealTimers();
    });

    function Probe() {
      query = useScene();
      return <output data-status={query.status}>{query.error?.message ?? (query.data?.building ? "Building" : "Ready")}</output>;
    }

    async function advance(ms: number) {
      await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    }

    async function render() {
      await act(async () => { root.render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>); });
      await advance(1); // React Query batches observer notifications onto its scheduler.
    }

    it("keeps a 202 → 500 build failure visible without retrying or polling stale building data", async () => {
      const building = { ...body, cache: { state: "building", built_ms: null } };
      fetcher
        .mockResolvedValueOnce(jsonResponse(202, building))
        .mockResolvedValueOnce(jsonResponse(500, { detail: "Atlas label generation failed" }))
        // The real server consumes its failure on the 500: an unintended third call would
        // start another build and return 202, concealing the error behind "Building…" again.
        .mockImplementation(async () => jsonResponse(202, building));
      await render();
      expect(fetcher).toHaveBeenCalledTimes(1);
      expect(fetcher.mock.calls[0]?.[0]).toBe(path);
      expect(query.data?.building).toBe(true);
      expect(container.textContent).toBe("Building");

      await advance(1001); // The route's one-second Retry-After expires once.
      expect(fetcher).toHaveBeenCalledTimes(2);
      // More than all three default retry delays and many poll intervals. Neither mechanism
      // may convert this consumed server failure into another automatically requested build.
      await advance(15_000);
      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(query.status).toBe("error");
      expect(query.error).toBeInstanceOf(SceneError);
      expect(query.error).toMatchObject({ status: 500, message: "Atlas label generation failed" });
      expect(container.textContent).toBe("Atlas label generation failed");
      expect(query.data?.building, "the stale 202 remains cached, but cannot keep polling").toBe(true);

      fetcher.mockImplementation(async () => jsonResponse(200, body));
      await act(async () => { await query.refetch(); });
      await advance(1);
      expect(fetcher).toHaveBeenCalledTimes(3);
      expect(query.status).toBe("success");
      expect(query.error).toBeNull();
      expect(query.data).toEqual({ ...body, building: false });
      expect(container.textContent).toBe("Ready");
      await advance(5000);
      expect(fetcher).toHaveBeenCalledTimes(3);
    });

    it("does not retry a readable 404", async () => {
      fetcher.mockImplementation(async () => jsonResponse(404, { detail: "The selected subject has no cortical atlas" }));
      await render();
      await advance(15_000);
      expect(fetcher).toHaveBeenCalledTimes(1);
      expect(query.error).toMatchObject({ status: 404, message: "The selected subject has no cortical atlas" });
      expect(container.textContent).toBe("The selected subject has no cortical atlas");
    });

    it("bounds transport failures to three retries and then leaves the error visible", async () => {
      const networkError = new TypeError("Network connection interrupted");
      fetcher.mockRejectedValue(networkError);
      await render();
      await advance(15_000);
      expect(fetcher).toHaveBeenCalledTimes(4); // Initial request plus three network-only retries.
      expect(query.error).toBe(networkError);
      expect(container.textContent).toBe("Network connection interrupted");
      await advance(15_000);
      expect(fetcher).toHaveBeenCalledTimes(4);
    });
  });
}
