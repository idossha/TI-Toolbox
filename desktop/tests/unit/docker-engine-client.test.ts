import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { startFakeEngineApi } from "../e2e/fixtures/fake-engine-api.mjs";
import { DockerEngineClient, DockerEngineError, type DockerConnection, type LogFrame } from "../../src/main/docker/engine";
import { StackApi } from "../../src/main/docker/stackApi";

/** Draining an async generator into an array — every streaming method under test returns one. */
async function collect<T>(gen: AsyncGenerator<T, void, void>, max = Infinity): Promise<T[]> {
  const out: T[] = [];
  for await (const item of gen) {
    out.push(item);
    if (out.length >= max) break;
  }
  return out;
}

/**
 * Containers are created and inspected through `StackApi`, the way `stack.ts` splits the work: this
 * client only starts, stops, removes and reads logs, so those are what is asserted on it here.
 */
describe("DockerEngineClient against a fake Engine API over a real Unix socket", () => {
  let fake: Awaited<ReturnType<typeof startFakeEngineApi>>;
  let conn: DockerConnection;
  let client: DockerEngineClient;
  let api: StackApi;

  beforeEach(async () => {
    fake = await startFakeEngineApi();
    conn = { kind: "unix", socketPath: fake.socketPath };
    client = new DockerEngineClient(conn, { timeoutMs: 5000 });
    api = new StackApi(conn, "1.51");
  });

  afterEach(async () => {
    await fake.close();
  });

  it("version() negotiates the API version from the daemon's own report", async () => {
    const v = await client.version();
    expect(v.ApiVersion).toBe("1.51");
    expect(v.Os).toBe("linux");
  });

  it("pullImage() streams NDJSON progress events, ending with a Status line", async () => {
    const events: string[] = [];
    await client.pullImage("alpine", "3.20", (e) => events.push(e.status));
    expect(events.length).toBeGreaterThanOrEqual(4);
    expect(events.at(-1)).toContain("Status: Downloaded newer image");
    expect(events.some((s) => s === "Downloading")).toBe(true);
  });

  // The image is amd64-only: an unpinned pull on Apple Silicon fails against an OCI index
  // ("no matching manifest for linux/arm64/v8"), so every pull must name the platform.
  it("pullImage() requests platform linux/amd64 by default", async () => {
    await client.pullImage("idossha/ti-toolbox", "v3.0.0");
    expect(fake.pulls).toEqual([{ image: "idossha/ti-toolbox", tag: "v3.0.0", platform: "linux/amd64" }]);
  });

  it("pullImage() throws on a mid-stream {error: ...} object even though the HTTP status was 200", async () => {
    await expect(client.pullImage("fixture/midstream-error", "latest")).rejects.toThrow(/manifest unknown/);
  });

  it("pullImage() maps an immediate 404 (unknown repository) to DockerErrorKind 'not-found'", async () => {
    const err = await client.pullImage("fixture/404-on-pull", "latest").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(DockerEngineError);
    expect((err as DockerEngineError).kind).toBe("not-found");
    expect((err as DockerEngineError).statusCode).toBe(404);
  });

  it("container lifecycle: start -> demuxed logs -> exit -> remove", async () => {
    const created = await api.createContainer(
      { Image: "alpine:3.20", Cmd: ["sh", "-c", "echo out; echo err 1>&2; exit 3"], Labels: { "fixture.exitCode": "3", "fixture.execDelayMs": "30" } },
      { name: "lifecycle" },
    );

    await client.startContainer(created.Id);
    expect((await api.inspect(created.Id)).running).toBe(true);

    const frames = await collect(client.logs(created.Id, { follow: false }));
    const byStream: Record<string, string> = {};
    for (const f of frames) byStream[f.stream] = (byStream[f.stream] ?? "") + f.payload.toString("utf8");
    expect(byStream.stdout).toBe("out\n");
    expect(byStream.stderr).toBe("err\n");

    // Following the log to its end is how the stack learns the container exited.
    await collect(client.logs(created.Id, { follow: true }));
    const exited = await api.inspect(created.Id);
    expect(exited.running).toBe(false);
    expect(exited.exitCode).toBe(3);

    await client.removeContainer(created.Id);
    await expect(api.inspect(created.Id)).rejects.toMatchObject({ kind: "not-found" });
  });

  it("logs({follow: true}) stays open until the container exits, then the generator ends", async () => {
    const created = await api.createContainer({ Image: "alpine:3.20", Cmd: ["true"], Labels: { "fixture.execDelayMs": "25" } }, { name: "follow" });
    await client.startContainer(created.Id);
    const frames: LogFrame[] = [];
    const started = Date.now();
    for await (const f of client.logs(created.Id, { follow: true })) frames.push(f);
    expect(Date.now() - started).toBeGreaterThanOrEqual(20); // proves it actually waited for exit, not an instant EOF
    expect(frames.map((f) => f.stream)).toEqual(["stdout", "stderr"]);
  });

  it("stopContainer() stops a running container cleanly (exit code 0, not a SIGKILL's 137)", async () => {
    const created = await api.createContainer({ Image: "alpine:3.20", Cmd: ["sleep", "999"], Labels: { "fixture.execDelayMs": "999999" } }, { name: "long" });
    await client.startContainer(created.Id);
    await client.stopContainer(created.Id, 1);
    const stopped = await api.inspect(created.Id);
    expect(stopped.running).toBe(false);
    expect(stopped.status).toBe("exited");
    expect(stopped.exitCode).toBe(0);
  });

  // `StackManager.stop()` treats exactly this as "already gone": a container the user removed
  // themselves must surface as kind "not-found", not as a generic failure.
  it("removeContainer() of a container that no longer exists rejects with kind 'not-found' (HTTP 404)", async () => {
    const created = await api.createContainer({ Image: "alpine:3.20", Cmd: ["true"] }, { name: "gone" });
    await client.removeContainer(created.Id);
    const err = await client.removeContainer(created.Id).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(DockerEngineError);
    expect((err as DockerEngineError).kind).toBe("not-found");
    expect((err as DockerEngineError).statusCode).toBe(404);
  });
});

describe("DockerEngineClient error classification for a missing endpoint", () => {
  it("a missing Unix socket is not-installed; a missing named pipe is not-running (Docker Desktop is down)", async () => {
    const unix = new DockerEngineClient({ kind: "unix", socketPath: "/tmp/tit-definitely-missing-9f3a.sock" }, { timeoutMs: 2000 });
    await expect(unix.version()).rejects.toMatchObject({ name: "DockerEngineError", kind: "not-installed" });
    // On this Linux host the pipe path is just a nonexistent Unix socket path, so the same ENOENT
    // arrives; what the test pins is that the *kind* of the connection decides the classification.
    const pipe = new DockerEngineClient({ kind: "npipe", socketPath: "//./pipe/tit-definitely-missing-9f3a" }, { timeoutMs: 2000 });
    await expect(pipe.version()).rejects.toMatchObject({ name: "DockerEngineError", kind: "not-running" });
  });
});
