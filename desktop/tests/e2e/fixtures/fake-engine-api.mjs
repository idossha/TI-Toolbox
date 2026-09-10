/* eslint-disable no-undef -- plain ESM Node script, not part of the eslint.config.mjs project
   (which has no node-globals override for this directory, unlike the existing one for
   tests/mock-server); not touching that shared config to avoid colliding with other lanes'
   concurrent edits to it. */
/**
 * Fake Docker Engine API server, listening on a Unix socket, for `tests/unit/docker-engine-*.test.ts`,
 * `tests/unit/docker-stack.test.ts` and `tests/e2e/launcher.spec.ts`.
 *
 * A real tiny HTTP server bound to a real Unix socket path (there is no `docker` binary to fake any
 * more — the app never invokes the CLI beyond `docker context inspect`), answering the subset of the
 * Docker Engine REST API `desktop/src/main/docker/engine.ts` speaks: `/version`, `/_ping`, `/info`,
 * `POST /images/create` (NDJSON pull progress, including a mid-stream `{"error": ...}` case),
 * the container lifecycle (`create`/`start`/`wait`/`stop`/`kill`/remove/`json`), `GET .../logs`
 * (genuinely 8-byte-multiplexed framed, and genuinely written in multiple small `res.write()`
 * calls so a real socket read can split a frame's header from its payload — exercising the same
 * boundary `tests/unit/docker-engine-frames.test.ts` exercises synthetically), and `GET /events`.
 *
 * Deliberate fixture conventions for error-mapping tests (r5 §6 / brief step 3's "404/409/500
 * mapping"): creating a container with `Image: "fixture/409-on-create"` returns HTTP 409;
 * `"fixture/500-on-create"` returns HTTP 500; any request naming an unknown container id returns
 * HTTP 404. A container's `Labels["fixture.exitCode"]` controls the exit code `wait`/logs report
 * (default `"0"`); `Labels["fixture.execDelayMs"]` controls how long it stays "running" before
 * exiting (default 40ms).
 *
 * The stack lifecycle (`src/main/stack.ts`, `src/main/docker/stackApi.ts`) needs more of the API
 * than the job runner did, so this fixture also answers `GET /containers/json` (label-filtered),
 * `GET /images/{name}/json` (404 = "pull it"), `GET /networks`, `POST /networks/create` and
 * `POST /volumes/create`, honours `?name=`/`?platform=` on create, and reports `Config.Env`,
 * `Config.Labels`, `State.Health` and `NetworkSettings.Ports` on inspect.
 *
 * Options:
 *   `images`         — image references that already exist locally (everything else must be pulled).
 *   `autoExit`       — default true: a started container exits after `fixture.execDelayMs` (40ms),
 *                      which is what the job-runner tests want. A stack test passes `false` so the
 *                      container stays up like a real server, unless its own label asks otherwise.
 *   `serveTitServer` — on container start, listen on the container's own `TIT_SERVER_PORT` and
 *                      answer `/api/health`, `/api/version`, `/api/jobs`, `/auth/session` and `/`
 *                      the way `tit.server` does, using its `TIT_SERVER_TOKEN`. This is what makes
 *                      "the container" real enough for the launcher e2e: the published port the
 *                      fake engine reports is the port that server is actually listening on.
 *   `podman`         — report a Podman-flavoured `/version`, for the unsupported-engine path.
 *
 * `startFakeEngineApi()` returns `{ socketPath, close, containers }` — `containers` is the live
 * in-memory registry, exposed so a test can assert on server-side state directly instead of only
 * through the client's own responses.
 */
import { createServer } from "node:http";
import { existsSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomBytes } from "node:crypto";

function shortId() {
  return randomBytes(16).toString("hex");
}

function writeJson(res, statusCode, body) {
  const text = body === undefined ? "" : JSON.stringify(body);
  res.writeHead(statusCode, { "content-type": "application/json" });
  res.end(text);
}

/** Writes one Docker stream-multiplexed frame, splitting header and payload into two `write()` calls on purpose. */
function writeLogFrame(res, streamType, text) {
  const payload = Buffer.from(text, "utf8");
  const header = Buffer.alloc(8);
  header.writeUInt8(streamType, 0);
  header.writeUInt32BE(payload.length, 4);
  res.write(header);
  res.write(payload);
}

/** The single published host port in a create body's HostConfig.PortBindings, if there is one. */
function hostPortOf(spec) {
  const bindings = spec?.HostConfig?.PortBindings ?? {};
  for (const list of Object.values(bindings)) {
    const port = Number(list?.[0]?.HostPort);
    if (port) return port;
  }
  return null;
}

function writeNdjson(res, obj) {
  res.write(JSON.stringify(obj) + "\n");
}

export async function startFakeEngineApi(opts = {}) {
  const socketPath = opts.socketPath ?? join(tmpdir(), `fake-engine-${process.pid}-${shortId()}.sock`);
  if (existsSync(socketPath)) unlinkSync(socketPath);
  const localImages = new Set(opts.images ?? []);
  const autoExit = opts.autoExit !== false;

  /** id -> { Id, Image, Cmd, Env, Labels, running, exitCode, waiters: Array<(code:number)=>void> } */
  const containers = new Map();
  const networks = new Map();
  const volumes = new Map();
  /** Every request this fake answered, as "METHOD /path" — lets a test assert what did NOT happen. */
  const requests = [];

  function envOf(container, name) {
    const hit = (container.Env ?? []).find((e) => e.startsWith(`${name}=`));
    return hit ? hit.slice(name.length + 1) : undefined;
  }

  /** "The container": a minimal tit.server on the port the container's own env publishes. */
  function startTitServer(container) {
    const port = Number(envOf(container, "TIT_SERVER_PORT"));
    const token = envOf(container, "TIT_SERVER_TOKEN") ?? "";
    if (!port) return;
    const server = createServer((req, res) => {
      const url = new URL(req.url, "http://127.0.0.1");
      if (url.pathname === "/api/health") return writeJson(res, 200, { status: "ok", uptime_s: 1 });
      if (url.pathname === "/api/jobs") return writeJson(res, 200, opts.jobs ?? []);
      if (url.pathname === "/api/version") {
        if ((req.headers.authorization || "") !== `Bearer ${token}`) return writeJson(res, 401, { detail: "Unauthorized" });
        return writeJson(res, 200, { tit_version: "fake", server_api: "v1", schema_hash: "", python: "fake", simnibs: "fake" });
      }
      if (url.pathname === "/auth/session") {
        if (url.searchParams.get("token") !== token) return writeJson(res, 401, { detail: "Unauthorized" });
        res.writeHead(303, { "set-cookie": "tit_session=fake; HttpOnly; Path=/; SameSite=Strict", location: "/" });
        return res.end();
      }
      res.writeHead(200, { "content-type": "text/html" });
      res.end(`<!doctype html><title>fake tit.server</title><h1 data-testid="fake-server-home">fake tit.server (${container.Id.slice(0, 12)})</h1>`);
    });
    server.listen(port, "127.0.0.1");
    container.titServer = server;
    container.publishedPort = port;
  }

  function stopTitServer(container) {
    if (container.titServer) {
      container.titServer.close();
      container.titServer = null;
    }
  }

  function scheduleExit(container) {
    const declared = container.Labels?.["fixture.execDelayMs"];
    if (!autoExit && declared === undefined) return; // stays up, like a real server
    const delay = Number(declared ?? 40);
    const exitCode = Number(container.Labels?.["fixture.exitCode"] ?? 0);
    setTimeout(() => {
      container.running = false;
      container.exitCode = exitCode;
      stopTitServer(container);
      for (const resolve of container.waiters.splice(0)) resolve(exitCode);
    }, delay);
  }

  const server = createServer((req, res) => {
    const url = new URL(req.url, "http://localhost");
    // Strip an optional /vX.YY version prefix, same as the real daemon accepting both forms.
    const path = url.pathname.replace(/^\/v[\d.]+/, "");
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const rawBody = Buffer.concat(chunks).toString("utf8");
      requests.push(`${req.method} ${path}`);
      handle(req.method, path, url, rawBody, res).catch((err) => {
        writeJson(res, 500, { message: `fake-engine-api internal error: ${err.message}` });
      });
    });
  });

  async function handle(method, path, url, rawBody, res) {
    if (method === "GET" && path === "/version") {
      if (opts.podman) {
        return writeJson(res, 200, {
          Version: "5.6.0",
          ApiVersion: "1.41",
          MinAPIVersion: "1.24",
          Os: "linux",
          Arch: "amd64",
          Components: [{ Name: "Podman Engine", Version: "5.6.0" }],
          Platform: { Name: "podman" },
        });
      }
      return writeJson(res, 200, { Version: "29.7.2-fake", ApiVersion: opts.apiVersion ?? "1.51", MinAPIVersion: "1.24", Os: "linux", Arch: "amd64" });
    }
    if (method === "GET" && path === "/_ping") {
      res.writeHead(200, { "content-type": "text/plain" });
      return res.end("OK");
    }
    if (method === "GET" && path === "/info") {
      return writeJson(res, 200, { ServerVersion: "29.7.2-fake", OperatingSystem: "Fake Linux", OSType: "linux", Architecture: "x86_64", NCPU: 4, MemTotal: 8_000_000_000 });
    }

    const imageInspect = path.match(/^\/images\/(.+)\/json$/);
    if (method === "GET" && imageInspect) {
      const ref = decodeURIComponent(imageInspect[1]);
      if (!localImages.has(ref)) return writeJson(res, 404, { message: `No such image: ${ref}` });
      return writeJson(res, 200, { Id: `sha256:${shortId()}`, RepoTags: [ref] });
    }

    if (method === "GET" && path === "/networks") {
      const filters = JSON.parse(url.searchParams.get("filters") ?? "{}");
      const wanted = filters.name ?? [];
      const all = [...networks.values()];
      return writeJson(res, 200, wanted.length ? all.filter((n) => wanted.includes(n.Name)) : all);
    }
    if (method === "POST" && path === "/networks/create") {
      const body = JSON.parse(rawBody || "{}");
      if ([...networks.values()].some((n) => n.Name === body.Name)) return writeJson(res, 409, { message: `network with name ${body.Name} already exists` });
      const id = shortId();
      networks.set(id, { Id: id, Name: body.Name, Driver: body.Driver ?? "bridge" });
      return writeJson(res, 201, { Id: id, Warning: "" });
    }
    if (method === "POST" && path === "/volumes/create") {
      const body = JSON.parse(rawBody || "{}");
      volumes.set(body.Name, { Name: body.Name, Driver: "local" });
      return writeJson(res, 201, { Name: body.Name, Driver: "local", Mountpoint: `/var/lib/docker/volumes/${body.Name}/_data` });
    }

    if (method === "GET" && path === "/containers/json") {
      const filters = JSON.parse(url.searchParams.get("filters") ?? "{}");
      const wantedLabels = (filters.label ?? []).map((entry) => entry.split("="));
      const all = url.searchParams.get("all") === "true" ? [...containers.values()] : [...containers.values()].filter((c) => c.running);
      const matching = all.filter((c) => wantedLabels.every(([k, v]) => c.Labels?.[k] === v));
      return writeJson(
        res,
        200,
        matching.map((c) => ({
          Id: c.Id,
          Names: [`/${c.Name ?? c.Id.slice(0, 12)}`],
          Image: c.Image,
          State: c.running ? "running" : c.started ? "exited" : "created",
          Status: c.running ? "Up 1 second" : "Created",
          Labels: c.Labels ?? {},
          Ports: c.publishedPort ? [{ IP: "127.0.0.1", PrivatePort: c.publishedPort, PublicPort: c.publishedPort, Type: "tcp" }] : [],
        })),
      );
    }

    if (method === "POST" && path === "/images/create") {
      const image = url.searchParams.get("fromImage") ?? "";
      const tag = url.searchParams.get("tag") ?? "latest";
      // Real Docker sometimes reports an unknown repo as a plain HTTP error before streaming
      // starts (rather than the mid-stream `{"error": ...}` shape `fixture/midstream-error`
      // below exercises) — checked, and the header written accordingly, before any body write.
      if (image === "fixture/404-on-pull") return writeJson(res, 404, { message: `pull access denied for ${image}, repository does not exist or may require 'docker login'` });
      res.writeHead(200, { "content-type": "application/json" });
      if (image === "fixture/midstream-error") {
        writeNdjson(res, { status: `Pulling from ${image}`, id: "layer1" });
        writeNdjson(res, { error: "manifest for fixture/midstream-error:latest not found: manifest unknown" });
        res.end();
        return;
      }
      writeNdjson(res, { status: `Pulling from ${image}`, id: "a1b2c3d4" });
      writeNdjson(res, { status: "Downloading", progressDetail: { current: 1024, total: 4096 }, id: "a1b2c3d4" });
      writeNdjson(res, { status: "Downloading", progressDetail: { current: 4096, total: 4096 }, id: "a1b2c3d4" });
      writeNdjson(res, { status: "Pull complete", id: "a1b2c3d4" });
      writeNdjson(res, { status: `Status: Downloaded newer image for ${image}:${tag}` });
      res.end();
      return;
    }

    if (method === "POST" && path === "/containers/create") {
      let spec;
      try {
        spec = JSON.parse(rawBody || "{}");
      } catch {
        return writeJson(res, 400, { message: "invalid JSON body" });
      }
      if (spec.Image === "fixture/409-on-create") return writeJson(res, 409, { message: "Conflict. The container name is already in use" });
      if (spec.Image === "fixture/500-on-create") return writeJson(res, 500, { message: "fake internal server error" });
      const name = url.searchParams.get("name") ?? undefined;
      if (name && [...containers.values()].some((c) => c.Name === name)) {
        return writeJson(res, 409, { message: `Conflict. The container name "/${name}" is already in use` });
      }
      const id = shortId();
      containers.set(id, {
        Id: id,
        Name: name,
        Platform: url.searchParams.get("platform") ?? undefined,
        Image: spec.Image,
        Cmd: spec.Cmd ?? [],
        Env: spec.Env ?? [],
        Labels: spec.Labels ?? {},
        HostConfig: spec.HostConfig ?? {},
        Healthcheck: spec.Healthcheck,
        publishedPort: hostPortOf(spec),
        running: false,
        started: false,
        exitCode: null,
        titServer: null,
        waiters: [],
      });
      return writeJson(res, 201, { Id: id, Warnings: [] });
    }

    const containerMatch = path.match(/^\/containers\/([^/]+)(\/.*)?$/);
    if (containerMatch) {
      const id = containerMatch[1];
      const sub = containerMatch[2] ?? "";
      const container = containers.get(id) ?? [...containers.values()].find((c) => c.Name === id);
      if (!container) return writeJson(res, 404, { message: `No such container: ${id}` });

      if (method === "POST" && sub === "/start") {
        container.running = true;
        container.started = true;
        if (opts.serveTitServer) startTitServer(container);
        scheduleExit(container);
        return writeJson(res, 204, undefined);
      }
      if (method === "POST" && sub === "/wait") {
        if (!container.running && container.exitCode !== null) return writeJson(res, 200, { StatusCode: container.exitCode });
        container.waiters.push((code) => writeJson(res, 200, { StatusCode: code }));
        return;
      }
      if (method === "POST" && sub === "/stop") {
        container.running = false;
        stopTitServer(container);
        container.exitCode = container.exitCode ?? 0;
        for (const resolve of container.waiters.splice(0)) resolve(container.exitCode);
        return writeJson(res, 204, undefined);
      }
      if (method === "POST" && sub === "/kill") {
        container.running = false;
        stopTitServer(container);
        container.exitCode = 137;
        for (const resolve of container.waiters.splice(0)) resolve(container.exitCode);
        return writeJson(res, 204, undefined);
      }
      if (method === "DELETE" && sub === "") {
        stopTitServer(container);
        containers.delete(container.Id);
        return writeJson(res, 204, undefined);
      }
      if (method === "GET" && sub === "/json") {
        const ports = {};
        if (container.publishedPort) {
          ports[`${container.publishedPort}/tcp`] = [{ HostIp: "127.0.0.1", HostPort: String(container.publishedPort) }];
        }
        return writeJson(res, 200, {
          Id: container.Id,
          Name: `/${container.Name ?? container.Id.slice(0, 12)}`,
          State: {
            Status: container.running ? "running" : container.started ? "exited" : "created",
            Running: container.running,
            ExitCode: container.exitCode ?? 0,
            ...(container.Healthcheck ? { Health: { Status: container.running ? "healthy" : "unhealthy" } } : {}),
          },
          Config: { Image: container.Image, Labels: container.Labels, Env: container.Env },
          HostConfig: container.HostConfig ?? {},
          NetworkSettings: { Ports: ports },
        });
      }
      if (method === "GET" && sub === "/logs") {
        res.writeHead(200, { "content-type": "application/vnd.docker.multiplexed-stream" });
        const stdoutText = container.Labels["fixture.stdout"] ?? "out\n";
        const stderrText = container.Labels["fixture.stderr"] ?? "err\n";
        writeLogFrame(res, 1, stdoutText);
        writeLogFrame(res, 2, stderrText);
        const follow = url.searchParams.get("follow") === "true";
        if (follow && container.running) {
          const onExit = () => res.end();
          container.waiters.push(onExit);
        } else {
          res.end();
        }
        return;
      }
    }

    if (method === "GET" && path === "/events") {
      res.writeHead(200, { "content-type": "application/json" });
      const lastId = [...containers.keys()].pop() ?? "unknown";
      writeNdjson(res, { Type: "container", Action: "start", Actor: { ID: lastId, Attributes: {} }, time: Math.floor(Date.now() / 1000) });
      setTimeout(() => {
        writeNdjson(res, { Type: "container", Action: "die", Actor: { ID: lastId, Attributes: { exitCode: "0" } }, time: Math.floor(Date.now() / 1000) });
        setTimeout(() => res.end(), 20);
      }, 20);
      return;
    }

    return writeJson(res, 404, { message: `fake-engine-api: unhandled route ${method} ${path}` });
  }

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(socketPath, resolve);
  });

  async function close() {
    for (const container of containers.values()) stopTitServer(container);
    await new Promise((resolve) => server.close(() => resolve()));
    if (existsSync(socketPath)) unlinkSync(socketPath);
  }

  return { socketPath, close, containers, networks, volumes, requests, server };
}
