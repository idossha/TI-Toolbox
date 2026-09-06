/**
 * Type declarations for `fake-engine-api.mjs` (a plain ESM script, not TypeScript) so
 * `tests/unit/docker-engine-client.test.ts` and `tests/unit/docker-stack.test.ts` type-check under
 * `tsconfig.web.json` without `allowJs`. Kept minimal — only the shape the tests actually touch.
 */
import type { Server } from "node:http";

export interface FakeEngineApiContainer {
  Id: string;
  Name?: string;
  Platform?: string;
  Image?: string;
  Cmd: string[];
  Env: string[];
  Labels: Record<string, string>;
  HostConfig?: Record<string, unknown>;
  Healthcheck?: Record<string, unknown>;
  publishedPort: number | null;
  running: boolean;
  started: boolean;
  exitCode: number | null;
}

export interface FakeEngineApiNetwork {
  Id: string;
  Name: string;
  Driver: string;
}

export interface FakeEngineApiVolume {
  Name: string;
  Driver: string;
}

export interface FakeEngineApi {
  socketPath: string;
  close: () => Promise<void>;
  containers: Map<string, FakeEngineApiContainer>;
  networks: Map<string, FakeEngineApiNetwork>;
  volumes: Map<string, FakeEngineApiVolume>;
  /** Every request answered, as "METHOD /path" (version prefix stripped). */
  requests: string[];
  server: Server;
}

export interface FakeEngineApiOptions {
  socketPath?: string;
  /** Image references that already exist locally; anything else must be pulled. */
  images?: string[];
  /** Default true: a started container exits shortly after start. False keeps it up. */
  autoExit?: boolean;
  /** Listen on the started container's own `TIT_SERVER_PORT` and answer like `tit.server`. */
  serveTitServer?: boolean;
  /** Report a Podman-flavoured `/version` (the unsupported-engine path). */
  podman?: boolean;
  /** Override the reported `ApiVersion` (the too-old-engine path). */
  apiVersion?: string;
}

export function startFakeEngineApi(opts?: FakeEngineApiOptions): Promise<FakeEngineApi>;
