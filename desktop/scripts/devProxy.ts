/**
 * The Vite dev-server proxy for `/api`, `/auth` and `/ws` — and the one place the dev token is
 * spent (P2, `docs/dev/HISTORY.md § 2026-09-03 (pipelines program)` §2).
 *
 * The old dev loop made the *developer* carry the token: read it out of `docker inspect`, paste
 * `/auth/session?token=…` into a browser to mint a cookie, and export `TIT_DEV_ORIGINS=<vite
 * origin>` on the server so the cookie's CSRF check would accept requests whose `Origin` was
 * Vite's. Three manual steps, and all three came back after every `docker restart` — the server
 * forgets its sessions, so the tab 401s and the dance starts again.
 *
 * Instead the proxy stamps every proxied request with two headers:
 *
 *   Authorization: Bearer <token>   `tit/server/auth.py#require_auth` treats a matching bearer as
 *                                   sufficient outright, cookie or no cookie, so the page needs no
 *                                   session at all and a server restart cannot log it out.
 *   Origin: <server origin>         `changeOrigin: true` rewrites `Host` to the target but leaves
 *                                   the browser's own `Origin: http://127.0.0.1:5173` in place, so
 *                                   `origin_allowed()` (WS) and `_cookie_csrf_ok()` (mutations)
 *                                   would see origin≠host and 403. Rewriting it to the target's own
 *                                   origin makes every proxied request look like what it is: a
 *                                   local process talking to the server, not a browser page from
 *                                   another origin.
 *
 * Both are set on `proxyReq` *and* `proxyReqWs`. Only the first fires for plain HTTP; only the
 * second fires for the `/ws/system` upgrade, and a WebSocket that never gets the bearer is the
 * failure this file exists to prevent — the page loads, the jobs rail stays empty, and nothing in
 * the console says why.
 *
 * The token is never written to disk and never reaches the renderer: `scripts/dev.ts` recovers it
 * from the container and passes it to Vite in the child environment only.
 */
import type { ProxyOptions } from "vite";

/** The one method this module calls on http-proxy's outgoing request. */
export interface HeaderSink {
  setHeader(name: string, value: string): void;
}

/** The one method this module calls on the http-proxy server handed to `configure`. */
export interface ProxyEventSink {
  on(event: "proxyReq" | "proxyReqWs", handler: (proxyReq: HeaderSink) => void): unknown;
}

export interface DevProxyInput {
  /** Where `/api`, `/auth` and `/ws` are forwarded, e.g. `http://127.0.0.1:8765`. */
  target: string;
  /** Bearer token to inject. Empty string injects no `Authorization` header at all. */
  token: string;
  /**
   * `server.proxy`'s bypass: return a path to serve locally instead of proxying. The renderer's
   * own source lives under `src/renderer/api/` and `src/renderer/ws/`, which collide with the
   * server's route prefixes — see `electron.vite.config.ts#serveRendererSource`.
   */
  bypass?: ProxyOptions["bypass"];
}

/**
 * Registers the two header stamps on one http-proxy server. Exported separately from
 * `createDevProxy` so `tests/unit/dev-proxy.test.ts` can drive it with a fake proxy and a fake
 * request and read the headers back — no Vite, no network, no container.
 */
export function attachDevAuth(proxy: ProxyEventSink, target: string, token: string): void {
  const origin = new URL(target).origin;
  const stamp = (proxyReq: HeaderSink): void => {
    if (token) proxyReq.setHeader("Authorization", `Bearer ${token}`);
    proxyReq.setHeader("Origin", origin);
  };
  proxy.on("proxyReq", stamp);
  proxy.on("proxyReqWs", stamp);
}

/** Authenticated API and WebSocket proxies for the renderer dev server. */
export function createDevProxy(input: DevProxyInput): Record<string, ProxyOptions> {
  const entry = (ws: boolean): ProxyOptions => ({
    target: input.target,
    changeOrigin: true,
    ...(ws ? { ws: true } : {}),
    ...(input.bypass ? { bypass: input.bypass } : {}),
    configure: (proxy) => attachDevAuth(proxy as unknown as ProxyEventSink, input.target, input.token),
  });
  return { "/api": entry(false), "/auth": entry(false), "/ws": entry(true) };
}
