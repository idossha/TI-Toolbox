/**
 * The dev proxy's two header stamps (`scripts/devProxy.ts`), proved against a fake http-proxy
 * object and a fake outgoing request. No Vite, no network, no container.
 *
 * Why this is a test and not a comment: the headers are invisible in the browser (they are added
 * after the request leaves the page) and their absence fails *silently* — a missing `Authorization`
 * shows as a 401 the renderer reports as "not connected", and a missing `Origin` rewrite shows as a
 * WebSocket that never opens and a jobs rail that stays empty. The `proxyReqWs` half is the one
 * that got forgotten in the first draft of this design; it has its own assertion here.
 */
import { describe, expect, it } from "vitest";
import { attachDevAuth, createDevProxy, type HeaderSink, type ProxyEventSink } from "../../scripts/devProxy";

/** Records what `attachDevAuth` registers and lets a test fire one of the two events. */
function fakeProxy(): ProxyEventSink & { fire(event: "proxyReq" | "proxyReqWs"): Record<string, string> } {
  const handlers = new Map<string, (proxyReq: HeaderSink) => void>();
  return {
    on(event, handler) {
      handlers.set(event, handler);
      return this;
    },
    fire(event) {
      const headers: Record<string, string> = {};
      const handler = handlers.get(event);
      if (!handler) throw new Error(`nothing registered for "${event}"`);
      handler({ setHeader: (name, value) => (headers[name] = value) });
      return headers;
    },
  };
}

describe("attachDevAuth", () => {
  it("stamps bearer + server Origin on a plain HTTP request", () => {
    const proxy = fakeProxy();
    attachDevAuth(proxy, "http://127.0.0.1:8765", "s3cret");
    expect(proxy.fire("proxyReq")).toEqual({ Authorization: "Bearer s3cret", Origin: "http://127.0.0.1:8765" });
  });

  it("stamps the same two headers on the WebSocket upgrade", () => {
    const proxy = fakeProxy();
    attachDevAuth(proxy, "http://127.0.0.1:8765", "s3cret");
    expect(proxy.fire("proxyReqWs")).toEqual({ Authorization: "Bearer s3cret", Origin: "http://127.0.0.1:8765" });
  });

  it("uses the target's ORIGIN, not the raw target string", () => {
    // `changeOrigin` rewrites Host to host:port; an Origin carrying a path would never match it,
    // and tit/server's origin_allowed() compares the two.
    const proxy = fakeProxy();
    attachDevAuth(proxy, "http://127.0.0.1:8766/some/path", "t");
    expect(proxy.fire("proxyReq").Origin).toBe("http://127.0.0.1:8766");
  });

  it("omits Authorization entirely when there is no token, and still fixes Origin", () => {
    // A bare `electron-vite dev` against the mock server has no token; sending "Bearer " would
    // turn a working cookie session into a 401.
    const proxy = fakeProxy();
    attachDevAuth(proxy, "http://127.0.0.1:8790", "");
    expect(proxy.fire("proxyReq")).toEqual({ Origin: "http://127.0.0.1:8790" });
  });
});

describe("createDevProxy", () => {
  it("covers exactly /api, /auth, /ws and /tetravox, and only /ws upgrades", () => {
    const proxy = createDevProxy({ target: "http://127.0.0.1:8765", token: "t" });
    expect(Object.keys(proxy).sort()).toEqual(["/api", "/auth", "/tetravox", "/ws"]);
    expect(proxy["/tetravox"]?.ws).toBeUndefined();
    expect(proxy["/ws"]?.ws).toBe(true);
    expect(proxy["/api"]?.ws).toBeUndefined();
  });

  it("keeps changeOrigin and passes the renderer-source bypass through to every entry", () => {
    // Losing the bypass is the failure that turns /api/client.ts into a 404 from the container and
    // leaves the page mounting nothing (electron.vite.config.ts#serveRendererSource).
    const bypass = (): string | null => "/api/client.ts";
    const proxy = createDevProxy({ target: "http://127.0.0.1:8765", token: "t", bypass });
    for (const key of ["/api", "/auth", "/ws", "/tetravox"]) {
      expect(proxy[key]?.changeOrigin).toBe(true);
      expect(proxy[key]?.bypass).toBe(bypass);
    }
  });

  it("installs the stamps through each entry's configure hook", () => {
    const proxy = createDevProxy({ target: "http://127.0.0.1:8765", token: "tok" });
    for (const key of ["/api", "/auth", "/ws", "/tetravox"]) {
      const fake = fakeProxy();
      const configure = proxy[key]?.configure;
      expect(configure).toBeTypeOf("function");
      (configure as unknown as (p: ProxyEventSink, o: unknown) => void)(fake, {});
      expect(fake.fire("proxyReqWs")).toEqual({ Authorization: "Bearer tok", Origin: "http://127.0.0.1:8765" });
    }
  });
});
