/**
 * Reads the repository's root `docker-compose.yml` — the stack definition — into a typed `Stack`, and turns
 * that `Stack` into the exact body the Docker Engine API's `POST /containers/create` wants.
 *
 * Compose stays the definition (plan of record D4); the Engine API is the driver. Nothing here
 * shells out to `docker compose`: the app parses the file itself so it can create the container
 * with its own labels, its own name and its own env map, and so a key the app does not implement
 * fails loudly at startup instead of being silently dropped by a CLI that understands more of the
 * Compose Spec than this app does.
 *
 * The supported subset is exactly the one in `docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)` §1:
 *
 *   services.<name>.{image, environment, volumes, ports, labels, healthcheck, command,
 *                    working_dir, init}  + platform, restart  (see SERVICE_KEYS)
 *   networks.<name>.{name, driver}
 *   volumes.<name>.{name}
 *
 * `platform` and `restart` are two additions to §1's list, both honoured rather than ignored:
 * `platform` is load-bearing on Apple Silicon (the image is `linux/amd64` and must be requested as
 * such on `POST /containers/create?platform=...`), and `restart` maps one-to-one onto
 * `HostConfig.RestartPolicy`. Every other key — at the top level, on a service, on a network or on
 * a volume — is a `StackError` naming the key, so an unimplemented Compose feature can never be
 * quietly ignored.
 *
 * Deliberately free of any `node:*`/`electron` import (like `compose.ts` and `paths.ts`): that
 * keeps it inside both `tsconfig.node.json`'s and `tsconfig.web.json`'s project, so
 * `tests/unit/composeFile.test.ts` type-checks and runs without Electron. Reading the file from
 * disk is `main/stack.ts`'s job; this module takes the text and an env map.
 */
import { parse as parseYaml } from "yaml";

/** A compose file this app cannot faithfully realise. `key` is the offending path, when there is one. */
export class StackError extends Error {
  readonly key: string | undefined;

  constructor(message: string, key?: string) {
    super(message);
    this.name = "StackError";
    this.key = key;
  }
}

// ---------------------------------------------------------------------------------------------
// The supported subset.
// ---------------------------------------------------------------------------------------------

const TOP_LEVEL_KEYS = new Set(["services", "networks", "volumes"]);
/** `version:` has been a no-op in the Compose Spec since Compose v2 — accepted and ignored, not honoured. */
const TOP_LEVEL_IGNORED = new Set(["version"]);
const SERVICE_KEYS = new Set([
  "image",
  "environment",
  "volumes",
  "ports",
  "labels",
  "healthcheck",
  "command",
  "working_dir",
  "init",
  "platform",
  "restart",
  "networks",
]);
const HEALTHCHECK_KEYS = new Set(["test", "interval", "timeout", "retries", "start_period", "disable"]);
const NETWORK_KEYS = new Set(["name", "driver"]);
const VOLUME_KEYS = new Set(["name"]);

// ---------------------------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------------------------

export interface StackBind {
  /** Host path, or the compose volume key when `named` is true. */
  source: string;
  target: string;
  readOnly: boolean;
  /** True when `source` names a top-level `volumes:` entry rather than a host path. */
  named: boolean;
}

export interface StackPort {
  hostIp: string;
  hostPort: number;
  containerPort: number;
  protocol: "tcp" | "udp";
}

export interface StackHealthcheck {
  test: string[];
  /** Docker's API takes durations in nanoseconds. */
  intervalNs?: number;
  timeoutNs?: number;
  startPeriodNs?: number;
  retries?: number;
}

export interface StackService {
  image: string;
  environment: Record<string, string>;
  volumes: StackBind[];
  ports: StackPort[];
  labels: Record<string, string>;
  healthcheck?: StackHealthcheck;
  command?: string[];
  workingDir?: string;
  init?: boolean;
  platform?: string;
  restart?: string;
  networks: string[];
}

export interface StackNetwork {
  /** Explicit `name:`, else undefined — the caller prefixes the project name. */
  name?: string;
  driver?: string;
}

export interface StackVolume {
  name?: string;
}

export interface Stack {
  services: Record<string, StackService>;
  networks: Record<string, StackNetwork>;
  volumes: Record<string, StackVolume>;
}

// ---------------------------------------------------------------------------------------------
// Interpolation
// ---------------------------------------------------------------------------------------------

const VAR_RE = /\$(?:\$|\{([A-Za-z_][A-Za-z0-9_]*)(?::?-([^}]*))?\}|([A-Za-z_][A-Za-z0-9_]*))/g;

/**
 * Compose-style `${VAR}` / `${VAR:-default}` / `${VAR-default}` / `$VAR` substitution, with `$$`
 * as the literal-dollar escape. An undefined variable with no default is a `StackError` naming it
 * rather than an empty string: every variable this app's compose file uses is one the app itself
 * supplies (`buildStackEnv`), so a missing one is a bug in the app, not a user's environment, and
 * silently mounting `""` or publishing port `""` is the worst possible way to report it.
 *
 * `:-` and `-` are both accepted and treated identically. Compose distinguishes them (empty-or-unset
 * vs unset), but every value this app passes is either absent or meaningfully non-empty, so the
 * distinction has no observable effect here and one behaviour is easier to reason about.
 */
export function interpolate(value: string, env: Record<string, string | undefined>, key?: string): string {
  return value.replace(VAR_RE, (match, braced: string | undefined, fallback: string | undefined, bare: string | undefined) => {
    if (match === "$$") return "$";
    const name = braced ?? bare ?? "";
    const found = env[name];
    if (found !== undefined && found !== "") return found;
    if (fallback !== undefined) return fallback;
    throw new StackError(`compose: \${${name}} is not set${key ? ` (in ${key})` : ""}`, key);
  });
}

function interpolateDeep(node: unknown, env: Record<string, string | undefined>, key: string): unknown {
  if (typeof node === "string") return interpolate(node, env, key);
  if (Array.isArray(node)) return node.map((item, i) => interpolateDeep(item, env, `${key}[${i}]`));
  if (node && typeof node === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) out[k] = interpolateDeep(v, env, `${key}.${k}`);
    return out;
  }
  return node;
}

// ---------------------------------------------------------------------------------------------
// Small parsers
// ---------------------------------------------------------------------------------------------

const DURATION_RE = /^(\d+(?:\.\d+)?)(ns|us|ms|s|m|h)$/;
const DURATION_NS: Record<string, number> = { ns: 1, us: 1e3, ms: 1e6, s: 1e9, m: 60e9, h: 3600e9 };

export function durationToNs(value: string, key: string): number {
  const match = DURATION_RE.exec(value.trim());
  const unit = match?.[2];
  if (!match || unit === undefined) throw new StackError(`compose: ${key} is not a duration like "10s": ${value}`, key);
  return Math.round(Number(match[1]) * (DURATION_NS[unit] ?? 1));
}

/**
 * POSIX-ish word splitting for compose's string (shell) form of `command:`. Handles single and
 * double quotes and backslash escapes — enough for the one-line `simnibs_python -m tit.server …`
 * shapes this file's `command` ever takes. Docker's `Config.Cmd` is a string array; compose does
 * the same split before handing it to the daemon.
 */
export function splitCommand(value: string, key = "command"): string[] {
  const out: string[] = [];
  let current = "";
  let quote: '"' | "'" | null = null;
  let started = false;
  for (let i = 0; i < value.length; i++) {
    const ch = value[i] as string;
    if (ch === "\\" && quote !== "'" && i + 1 < value.length) {
      current += value[++i];
      started = true;
      continue;
    }
    if (quote) {
      if (ch === quote) quote = null;
      else current += ch;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      started = true;
      continue;
    }
    if (/\s/.test(ch)) {
      if (started) out.push(current);
      current = "";
      started = false;
      continue;
    }
    current += ch;
    started = true;
  }
  if (quote) throw new StackError(`compose: ${key} has an unterminated ${quote} quote`, key);
  if (started) out.push(current);
  return out;
}

/** `SOURCE:TARGET[:ro|rw]`, tolerating a Windows `C:\...` drive-letter source. */
export function parseBind(value: string, key: string): StackBind {
  const drive = /^[A-Za-z]:[\\/]/.exec(value);
  const head = drive ? value.slice(0, 2) : "";
  const rest = drive ? value.slice(2) : value;
  const parts = rest.split(":");
  if (parts.length < 2 || parts.length > 3) throw new StackError(`compose: ${key} is not "source:target[:mode]": ${value}`, key);
  const source = head + (parts[0] ?? "");
  const target = parts[1] ?? "";
  const mode = parts[2];
  if (!source || !target) throw new StackError(`compose: ${key} has an empty source or target: ${value}`, key);
  if (mode !== undefined && mode !== "ro" && mode !== "rw") throw new StackError(`compose: ${key} has an unsupported mount mode "${mode}" (only ro/rw)`, key);
  return { source, target, readOnly: mode === "ro", named: false };
}

/**
 * `HOST_IP:HOST_PORT:CONTAINER_PORT[/proto]` only. A mapping without an explicit loopback host IP
 * is refused: the toolbox server holds a bearer token and mounts the user's data, and publishing it
 * on `0.0.0.0` would expose it to the local network (TODO §2.8). Making that a parse error rather
 * than a silent rewrite means the compose file has to say what it means.
 */
export function parsePort(value: string, key: string): StackPort {
  const [spec, protoRaw] = value.split("/");
  const protocol = (protoRaw ?? "tcp") as "tcp" | "udp";
  if (protocol !== "tcp" && protocol !== "udp") throw new StackError(`compose: ${key} has an unsupported protocol "${protoRaw}"`, key);
  const parts = (spec ?? "").split(":");
  if (parts.length !== 3) {
    throw new StackError(`compose: ${key} must be "127.0.0.1:HOST:CONTAINER" — this app never publishes a port on all interfaces: ${value}`, key);
  }
  const [hostIp, hostPortRaw, containerPortRaw] = parts as [string, string, string];
  if (hostIp !== "127.0.0.1" && hostIp !== "localhost" && hostIp !== "::1") {
    throw new StackError(`compose: ${key} publishes on ${hostIp}; only 127.0.0.1 is allowed: ${value}`, key);
  }
  const hostPort = Number(hostPortRaw);
  const containerPort = Number(containerPortRaw);
  if (!Number.isInteger(hostPort) || !Number.isInteger(containerPort)) throw new StackError(`compose: ${key} has a non-numeric port: ${value}`, key);
  return { hostIp: hostIp === "localhost" ? "127.0.0.1" : hostIp, hostPort, containerPort, protocol };
}

// ---------------------------------------------------------------------------------------------
// Section parsers
// ---------------------------------------------------------------------------------------------

function asRecord(node: unknown, key: string): Record<string, unknown> {
  if (!node || typeof node !== "object" || Array.isArray(node)) throw new StackError(`compose: ${key} must be a mapping`, key);
  return node as Record<string, unknown>;
}

function rejectUnknown(node: Record<string, unknown>, allowed: Set<string>, prefix: string, ignored?: Set<string>): void {
  for (const k of Object.keys(node)) {
    if (allowed.has(k) || ignored?.has(k)) continue;
    throw new StackError(`compose: ${prefix}${k} is not supported by this app`, `${prefix}${k}`);
  }
}

/** `{K: V}` or `["K=V", "K"]` — the two forms compose allows for `environment:` and `labels:`. */
function parseKeyValues(node: unknown, key: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (node === undefined || node === null) return out;
  if (Array.isArray(node)) {
    for (const entry of node) {
      const text = String(entry);
      const eq = text.indexOf("=");
      if (eq < 0) out[text] = "";
      else out[text.slice(0, eq)] = text.slice(eq + 1);
    }
    return out;
  }
  for (const [k, v] of Object.entries(asRecord(node, key))) out[k] = v === null || v === undefined ? "" : String(v);
  return out;
}

function parseHealthcheck(node: unknown, key: string): StackHealthcheck | undefined {
  const hc = asRecord(node, key);
  rejectUnknown(hc, HEALTHCHECK_KEYS, `${key}.`);
  if (hc.disable === true) return { test: ["NONE"] };
  const testNode = hc.test;
  let test: string[];
  if (typeof testNode === "string") test = ["CMD-SHELL", testNode];
  else if (Array.isArray(testNode)) test = testNode.map(String);
  else throw new StackError(`compose: ${key}.test must be a string or a list`, `${key}.test`);
  const out: StackHealthcheck = { test };
  if (hc.interval !== undefined) out.intervalNs = durationToNs(String(hc.interval), `${key}.interval`);
  if (hc.timeout !== undefined) out.timeoutNs = durationToNs(String(hc.timeout), `${key}.timeout`);
  if (hc.start_period !== undefined) out.startPeriodNs = durationToNs(String(hc.start_period), `${key}.start_period`);
  if (hc.retries !== undefined) out.retries = Number(hc.retries);
  return out;
}

function parseService(name: string, node: unknown, declaredVolumes: Set<string>): StackService {
  const key = `services.${name}`;
  const raw = asRecord(node, key);
  rejectUnknown(raw, SERVICE_KEYS, `${key}.`);
  if (typeof raw.image !== "string" || !raw.image) throw new StackError(`compose: ${key}.image is required`, `${key}.image`);

  const volumes = (Array.isArray(raw.volumes) ? raw.volumes : []).flatMap((entry, i): StackBind[] => {
    if (typeof entry !== "string") throw new StackError(`compose: ${key}.volumes[${i}] must use the short "source:target" form`, `${key}.volumes[${i}]`);
    // An *optional* mount: `${TIT_REPO_DIR:-}:/ti-toolbox` with the variable empty interpolates to
    // ":/ti-toolbox", and the whole entry is dropped. This is the only way a compose file can say
    // "mount this only in some runs" — Docker has no empty-source bind, and the alternative the app
    // shipped with (always supplying a non-empty `TIT_REPO_DIR`) bind-mounted a host directory over
    // the image's own baked-in `/ti-toolbox` on every single start, dev or packaged, silently
    // replacing the `tit` D1 says ships inside the image. An empty *target* is still an error:
    // that is a broken line, not an optional one.
    if (entry.startsWith(":")) return [];
    const bind = parseBind(entry, `${key}.volumes[${i}]`);
    return [declaredVolumes.has(bind.source) ? { ...bind, named: true } : bind];
  });

  const ports = (Array.isArray(raw.ports) ? raw.ports : []).map((entry, i) => parsePort(String(entry), `${key}.ports[${i}]`));

  let command: string[] | undefined;
  if (typeof raw.command === "string") command = splitCommand(raw.command, `${key}.command`);
  else if (Array.isArray(raw.command)) command = raw.command.map(String);
  else if (raw.command !== undefined) throw new StackError(`compose: ${key}.command must be a string or a list`, `${key}.command`);

  const service: StackService = {
    image: raw.image,
    environment: parseKeyValues(raw.environment, `${key}.environment`),
    volumes,
    ports,
    labels: parseKeyValues(raw.labels, `${key}.labels`),
    networks: Array.isArray(raw.networks) ? raw.networks.map(String) : [],
  };
  if (raw.healthcheck !== undefined) service.healthcheck = parseHealthcheck(raw.healthcheck, `${key}.healthcheck`);
  if (command) service.command = command;
  if (raw.working_dir !== undefined) service.workingDir = String(raw.working_dir);
  if (raw.init !== undefined) service.init = Boolean(raw.init);
  if (raw.platform !== undefined) service.platform = String(raw.platform);
  if (raw.restart !== undefined) service.restart = String(raw.restart);
  return service;
}

/**
 * Parses a compose file's text into a `Stack`, interpolating `${VAR}` from `env` first.
 *
 * Throws `StackError` — never a raw YAML error — for anything the app cannot realise, so
 * `stack.ts` has one error type to turn into launcher copy.
 */
export function parseComposeFile(text: string, env: Record<string, string | undefined>): Stack {
  let doc: unknown;
  try {
    doc = parseYaml(text);
  } catch (err) {
    throw new StackError(`compose: the file is not valid YAML: ${err instanceof Error ? err.message : String(err)}`);
  }
  const root = asRecord(interpolateDeep(asRecord(doc, "the compose file"), env, "compose"), "the compose file");
  rejectUnknown(root, TOP_LEVEL_KEYS, "", TOP_LEVEL_IGNORED);

  const volumes: Record<string, StackVolume> = {};
  for (const [name, node] of Object.entries(root.volumes ? asRecord(root.volumes, "volumes") : {})) {
    const entry = node === null || node === undefined ? {} : asRecord(node, `volumes.${name}`);
    rejectUnknown(entry, VOLUME_KEYS, `volumes.${name}.`);
    volumes[name] = entry.name !== undefined ? { name: String(entry.name) } : {};
  }

  const networks: Record<string, StackNetwork> = {};
  for (const [name, node] of Object.entries(root.networks ? asRecord(root.networks, "networks") : {})) {
    const entry = node === null || node === undefined ? {} : asRecord(node, `networks.${name}`);
    rejectUnknown(entry, NETWORK_KEYS, `networks.${name}.`);
    networks[name] = {
      ...(entry.name !== undefined ? { name: String(entry.name) } : {}),
      ...(entry.driver !== undefined ? { driver: String(entry.driver) } : {}),
    };
  }

  const declaredVolumes = new Set(Object.keys(volumes));
  const services: Record<string, StackService> = {};
  for (const [name, node] of Object.entries(asRecord(root.services, "services"))) {
    services[name] = parseService(name, node, declaredVolumes);
    for (const net of services[name]?.networks ?? []) {
      if (!(net in networks)) throw new StackError(`compose: services.${name}.networks names "${net}", which is not declared under networks`, `services.${name}.networks`);
    }
  }
  if (Object.keys(services).length === 0) throw new StackError("compose: no services are declared", "services");
  return { services, networks, volumes };
}

// ---------------------------------------------------------------------------------------------
// Stack -> Engine API
// ---------------------------------------------------------------------------------------------

/** The `POST /containers/create` body, as far as this app fills it in. */
export interface ContainerCreateBody {
  Image: string;
  Entrypoint?: string[];
  Cmd?: string[];
  Env: string[];
  Labels: Record<string, string>;
  WorkingDir?: string;
  Healthcheck?: { Test: string[]; Interval?: number; Timeout?: number; StartPeriod?: number; Retries?: number };
  ExposedPorts: Record<string, Record<string, never>>;
  HostConfig: {
    Binds: string[];
    DeviceRequests?: { Driver: string; Count: number; Capabilities: string[][] }[];
    Init?: boolean;
    NetworkMode?: string;
    RestartPolicy?: { Name: string; MaximumRetryCount?: number };
    PortBindings: Record<string, { HostIp: string; HostPort: string }[]>;
  };
  NetworkingConfig?: { EndpointsConfig: Record<string, Record<string, never>> };
}

export interface ContainerPlan {
  containerName: string;
  /** Image reference exactly as the compose file wrote it. */
  image: string;
  imageName: string;
  imageTag: string;
  platform: string | undefined;
  /** Resolved Docker network name, or null when the service declares none. */
  networkName: string | null;
  networkDriver: string;
  /** Resolved Docker names of the named volumes this service mounts. */
  namedVolumes: string[];
  hostPort: number;
  containerPort: number;
  body: ContainerCreateBody;
}

export interface ContainerPlanInput {
  serviceName: string;
  /** Compose project name — prefixes the container, network and volume names. */
  projectName: string;
  /** Labels merged over the service's own (`tit.project`, `tit.stack`, …). */
  labels: Record<string, string>;
}

function splitImageRef(image: string): { name: string; tag: string } {
  const slash = image.lastIndexOf("/");
  const colon = image.lastIndexOf(":");
  if (colon > slash) return { name: image.slice(0, colon), tag: image.slice(colon + 1) };
  return { name: image, tag: "latest" };
}

/** Resolved Docker object name for a top-level `volumes:`/`networks:` entry (compose's own rule). */
export function resolvedName(projectName: string, key: string, explicit?: string): string {
  return explicit ?? `${projectName}_${key}`;
}

/**
 * Turns one service of a parsed `Stack` into everything `stack.ts` needs to realise it through the
 * Engine API: the container-create body, plus the image/network/volume names it must ensure exist
 * first and the published port it will then poll for health.
 */
export function buildContainerPlan(stack: Stack, input: ContainerPlanInput): ContainerPlan {
  const service = stack.services[input.serviceName];
  if (!service) throw new StackError(`compose: no service named "${input.serviceName}"`, `services.${input.serviceName}`);
  if (service.ports.length !== 1) {
    throw new StackError(`compose: services.${input.serviceName} must publish exactly one port (found ${service.ports.length})`, `services.${input.serviceName}.ports`);
  }
  const port = service.ports[0] as StackPort;

  const networkKey = service.networks[0] ?? Object.keys(stack.networks)[0];
  const networkName = networkKey ? resolvedName(input.projectName, networkKey, stack.networks[networkKey]?.name) : null;
  const networkDriver = (networkKey ? stack.networks[networkKey]?.driver : undefined) ?? "bridge";

  const namedVolumes: string[] = [];
  const binds = service.volumes.map((bind) => {
    const source = bind.named ? resolvedName(input.projectName, bind.source, stack.volumes[bind.source]?.name) : bind.source;
    if (bind.named) namedVolumes.push(source);
    return `${source}:${bind.target}${bind.readOnly ? ":ro" : ""}`;
  });

  const portKey = `${port.containerPort}/${port.protocol}`;
  const { name: imageName, tag: imageTag } = splitImageRef(service.image);

  const body: ContainerCreateBody = {
    Image: service.image,
    Env: Object.entries(service.environment).map(([k, v]) => `${k}=${v}`),
    Labels: { ...service.labels, ...input.labels },
    ExposedPorts: { [portKey]: {} },
    HostConfig: {
      Binds: binds,
      PortBindings: { [portKey]: [{ HostIp: port.hostIp, HostPort: String(port.hostPort) }] },
      ...(service.init !== undefined ? { Init: service.init } : {}),
      ...(networkName ? { NetworkMode: networkName } : {}),
      ...(service.restart ? { RestartPolicy: restartPolicy(service.restart) } : {}),
    },
    ...(networkName ? { NetworkingConfig: { EndpointsConfig: { [networkName]: {} } } } : {}),
  };
  if (service.command) body.Cmd = service.command;
  if (service.workingDir) body.WorkingDir = service.workingDir;
  if (service.healthcheck) {
    body.Healthcheck = {
      Test: service.healthcheck.test,
      ...(service.healthcheck.intervalNs !== undefined ? { Interval: service.healthcheck.intervalNs } : {}),
      ...(service.healthcheck.timeoutNs !== undefined ? { Timeout: service.healthcheck.timeoutNs } : {}),
      ...(service.healthcheck.startPeriodNs !== undefined ? { StartPeriod: service.healthcheck.startPeriodNs } : {}),
      ...(service.healthcheck.retries !== undefined ? { Retries: service.healthcheck.retries } : {}),
    };
  }

  return {
    containerName: `${input.projectName}-${input.serviceName}-1`,
    image: service.image,
    imageName,
    imageTag,
    platform: service.platform,
    networkName,
    networkDriver,
    namedVolumes,
    hostPort: port.hostPort,
    containerPort: port.containerPort,
    body,
  };
}

function restartPolicy(value: string): { Name: string; MaximumRetryCount?: number } {
  const [name, count] = value.split(":");
  if (name === "on-failure" && count) return { Name: name, MaximumRetryCount: Number(count) };
  return { Name: name ?? "no" };
}
