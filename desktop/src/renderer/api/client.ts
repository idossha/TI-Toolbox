/**
 * Origin-relative typed client for the wire contract (contracts/openapi.yaml, generated into
 * ./schema.d.ts by `npm run gen:api`). Same code runs in Electron, in the Vite dev server (proxied)
 * and in browser mode, because every URL is relative to the page origin.
 */
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Version = components["schemas"]["Version"];
export type Capabilities = components["schemas"]["Capabilities"];
export type Project = components["schemas"]["Project"];
export type Subject = components["schemas"]["Subject"];
export type Simulation = components["schemas"]["Simulation"];
export type SystemSnapshot = components["schemas"]["SystemSnapshot"];
export type ProjectStorage = components["schemas"]["ProjectStorage"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly path: string,
    message?: string,
  ) {
    super(message ?? `${path} failed with HTTP ${status}`);
    this.name = "ApiError";
  }
}

type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

/** Subscribe to 401s from any request; used by the app shell to show the sign-in state. */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

const unauthorizedMiddleware: Middleware = {
  onResponse({ response }) {
    if (response.status === 401) for (const l of unauthorizedListeners) l();
    return response;
  },
};

/**
 * `baseUrl` is "" in production (origin-relative). Node's `Request` rejects relative URLs, so
 * tests pass an absolute base.
 */
export function createApi(opts: { fetch?: (input: Request) => Promise<Response>; baseUrl?: string } = {}) {
  const client = createClient<paths>({ baseUrl: opts.baseUrl ?? "", fetch: opts.fetch, credentials: "same-origin" });
  client.use(unauthorizedMiddleware);
  return client;
}

export const api = createApi();

/** Unwrap an openapi-fetch result into data or a thrown ApiError. */
export function unwrap<T>(
  result: { data?: T; error?: unknown; response: Response },
  path: string,
): T {
  if (result.response.ok && result.data !== undefined) return result.data;
  throw new ApiError(result.response.status, path);
}

export async function getVersion(client = api): Promise<Version> {
  return unwrap(await client.GET("/api/version"), "/api/version");
}

/** The project this server instance is bound to — the top bar shows `name` here (ra_12 #30; the
 * brand/wordmark itself stays only in the nav rail, `app/NavRail.tsx`). */
export async function getProject(client = api): Promise<Project> {
  return unwrap(await client.GET("/api/project"), "/api/project");
}

export async function getCapabilities(client = api): Promise<Capabilities> {
  return unwrap(await client.GET("/api/capabilities"), "/api/capabilities");
}

export async function getSubjects(client = api): Promise<Subject[]> {
  return unwrap(await client.GET("/api/catalog/subjects"), "/api/catalog/subjects").subjects;
}

export async function getSimulations(subject: string, client = api): Promise<Simulation[]> {
  return unwrap(
    await client.GET("/api/catalog/simulations", { params: { query: { subject } } }),
    "/api/catalog/simulations",
  ).simulations;
}

/**
 * End the cookie session (POST /auth/logout). A 401 means the server already forgot the session
 * (e.g. it restarted), which is the outcome we want, so it is not an error here.
 */
export async function logout(client = api): Promise<void> {
  const { response } = await client.POST("/auth/logout");
  if (!response.ok && response.status !== 401) throw new ApiError(response.status, "/auth/logout");
}

/** Origin-relative WebSocket URL for a path such as "/ws/system". */
export function wsUrl(path: string, loc: { protocol: string; host: string } = window.location): string {
  return (loc.protocol === "https:" ? "wss:" : "ws:") + "//" + loc.host + path;
}
