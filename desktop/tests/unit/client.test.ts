import { describe, expect, it, vi } from "vitest";
import { ApiError, createApi, getSimulations, getSubjects, getVersion, logout, onUnauthorized, wsUrl } from "../../src/renderer/api/client";

const BASE = "http://test";

/** A client whose fetch is a spy; production uses baseUrl "" (origin-relative), see createApi. */
function fakeClient(handler: (url: string, req: Request) => Response) {
  const fetch = vi.fn(async (req: Request) => handler(req.url, req));
  return { client: createApi({ fetch, baseUrl: BASE }), fetch };
}

const jsonResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("api client", () => {
  it("requests are origin-relative and typed", async () => {
    const { client, fetch } = fakeClient((url, req) => {
      expect(url).toBe(`${BASE}/api/version`);
      expect(req.credentials).toBe("same-origin");
      return jsonResponse(200, { tit_version: "3.0.0", server_api: "v0", schema_hash: "", python: "3.11", simnibs: null });
    });
    const version = await getVersion(client);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(version.tit_version).toBe("3.0.0");
    expect(version.simnibs).toBeNull();
  });

  it("query parameters are encoded", async () => {
    const { client } = fakeClient((url) => {
      expect(url).toBe(`${BASE}/api/catalog/simulations?subject=ernie`);
      return jsonResponse(200, { simulations: [{ name: "Thalamus", path: "/x", has_ti: true, has_mti: false }] });
    });
    const sims = await getSimulations("ernie", client);
    expect(sims).toHaveLength(1);
    expect(sims[0]?.name).toBe("Thalamus");
  });

  it("401 throws ApiError and notifies unauthorized listeners", async () => {
    const listener = vi.fn();
    const off = onUnauthorized(listener);
    const { client } = fakeClient(() => jsonResponse(401, { detail: "not authenticated" }));
    await expect(getSubjects(client)).rejects.toMatchObject({ name: "ApiError", status: 401, path: "/api/catalog/subjects" });
    expect(listener).toHaveBeenCalledTimes(1);
    off();
  });

  it("404 throws ApiError without notifying", async () => {
    const listener = vi.fn();
    const off = onUnauthorized(listener);
    const { client } = fakeClient(() => jsonResponse(404, { detail: "unknown subject" }));
    const err = await getSimulations("nobody", client).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect(listener).not.toHaveBeenCalled();
    off();
  });

  it("logout POSTs /auth/logout and tolerates an already-forgotten session", async () => {
    const seen: string[] = [];
    const { client, fetch } = fakeClient((url, req) => {
      seen.push(`${req.method} ${url}`);
      return new Response(null, { status: seen.length === 1 ? 204 : 401 });
    });
    await logout(client);
    await logout(client); // 401: the server already forgot the session
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(seen).toEqual([`POST ${BASE}/auth/logout`, `POST ${BASE}/auth/logout`]);
  });

  it("logout rethrows other failures as ApiError", async () => {
    const { client } = fakeClient(() => new Response("boom", { status: 500 }));
    await expect(logout(client)).rejects.toMatchObject({ name: "ApiError", status: 500, path: "/auth/logout" });
  });

  it("wsUrl follows the page protocol and host", () => {
    expect(wsUrl("/ws/system", { protocol: "http:", host: "127.0.0.1:8765" })).toBe("ws://127.0.0.1:8765/ws/system");
    expect(wsUrl("/ws/system", { protocol: "https:", host: "lab.example" })).toBe("wss://lab.example/ws/system");
  });
});
