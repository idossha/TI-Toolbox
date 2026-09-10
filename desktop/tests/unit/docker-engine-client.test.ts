import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { startFakeEngineApi } from "../e2e/fixtures/fake-engine-api.mjs";
import { DockerEngineClient, DockerEngineError, runJobContainer, type DockerConnection, type LogFrame } from "../../src/main/docker/engine";

/** Draining an async generator into an array — every streaming method under test returns one. */
async function collect<T>(gen: AsyncGenerator<T, void, void>, max = Infinity): Promise<T[]> {
  const out: T[] = [];
  for await (const item of gen) {
    out.push(item);
    if (out.length >= max) break;
  }
  return out;
}

describe("DockerEngineClient against a fake Engine API over a real Unix socket", () => {
  let fake: Awaited<ReturnType<typeof startFakeEngineApi>>;
  let conn: DockerConnection;
  let client: DockerEngineClient;

  beforeEach(async () => {
    fake = await startFakeEngineApi();
    conn = { kind: "unix", socketPath: fake.socketPath };
    client = new DockerEngineClient(conn, { timeoutMs: 5000 });
  });

  afterEach(async () => {
    await fake.close();
  });

  it("version() negotiates the API version from the daemon's own report", async () => {
    const v = await client.version();
    expect(v.ApiVersion).toBe("1.51");
    expect(v.Os).toBe("linux");
  });

  it("info() and ping() work, and ping() never throws", async () => {
    const info = await client.info();
    expect(info.NCPU).toBe(4);
    expect(await client.ping()).toBe(true);
  });

  it("ping() returns false (not a throw) against a socket path nothing is listening on", async () => {
    const deadClient = new DockerEngineClient({ kind: "unix", socketPath: "/tmp/tit-nothing-here.sock" }, { timeoutMs: 1000 });
    expect(await deadClient.ping()).toBe(false);
  });

  it("pullImage() streams NDJSON progress events, ending with a Status line", async () => {
    const events: string[] = [];
    await client.pullImage("alpine", "3.20", (e) => events.push(e.status));
    expect(events.length).toBeGreaterThanOrEqual(4);
    expect(events.at(-1)).toContain("Status: Downloaded newer image");
    expect(events.some((s) => s === "Downloading")).toBe(true);
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

  it("full container lifecycle: create -> start -> demuxed logs -> wait -> remove", async () => {
    const created = await client.createContainer({
      Image: "alpine:3.20",
      Cmd: ["sh", "-c", "echo out; echo err 1>&2; sleep 1; exit 3"],
      Tty: false,
      Labels: { "fixture.exitCode": "3", "fixture.execDelayMs": "30" },
    });
    expect(created.Id).toMatch(/^[0-9a-f]{32}$/);

    await client.startContainer(created.Id);
    const inspectedRunning = await client.inspectContainer(created.Id);
    expect(inspectedRunning.State.Running).toBe(true);

    const frames = await collect(client.logs(created.Id, { follow: false }));
    const byStream: Record<string, string> = {};
    for (const f of frames) byStream[f.stream] = (byStream[f.stream] ?? "") + f.payload.toString("utf8");
    expect(byStream.stdout).toBe("out\n");
    expect(byStream.stderr).toBe("err\n");

    const result = await client.waitContainer(created.Id);
    expect(result.StatusCode).toBe(3);

    const inspectedExited = await client.inspectContainer(created.Id);
    expect(inspectedExited.State.Running).toBe(false);
    expect(inspectedExited.State.ExitCode).toBe(3);

    await client.removeContainer(created.Id);
    await expect(client.inspectContainer(created.Id)).rejects.toMatchObject({ kind: "not-found", statusCode: 404 });
  });

  it("logs({follow: true}) stays open until the container exits, then the generator ends", async () => {
    const created = await client.createContainer({ Image: "alpine:3.20", Cmd: ["true"], Labels: { "fixture.execDelayMs": "25" } });
    await client.startContainer(created.Id);
    const frames: LogFrame[] = [];
    const started = Date.now();
    for await (const f of client.logs(created.Id, { follow: true })) frames.push(f);
    expect(Date.now() - started).toBeGreaterThanOrEqual(20); // proves it actually waited for exit, not an instant EOF
    expect(frames.map((f) => f.stream)).toEqual(["stdout", "stderr"]);
  });

  it("stopContainer() resolves an in-flight wait()", async () => {
    const created = await client.createContainer({ Image: "alpine:3.20", Cmd: ["sleep", "999"], Labels: { "fixture.execDelayMs": "999999" } });
    await client.startContainer(created.Id);
    const waitPromise = client.waitContainer(created.Id);
    await client.stopContainer(created.Id, 1);
    const result = await waitPromise;
    expect(result.StatusCode).toBe(0);
  });

  it("killContainer() reports exit code 137, matching a real SIGKILL", async () => {
    const created = await client.createContainer({ Image: "alpine:3.20", Cmd: ["sleep", "999"], Labels: { "fixture.execDelayMs": "999999" } });
    await client.startContainer(created.Id);
    await client.killContainer(created.Id);
    const inspected = await client.inspectContainer(created.Id);
    expect(inspected.State.ExitCode).toBe(137);
  });

  it("createContainer() maps HTTP 409 to DockerErrorKind 'conflict' and 500 to 'server-error'", async () => {
    const conflictErr = await client.createContainer({ Image: "fixture/409-on-create" }).catch((e: unknown) => e);
    expect(conflictErr).toBeInstanceOf(DockerEngineError);
    expect((conflictErr as DockerEngineError).kind).toBe("conflict");
    expect((conflictErr as DockerEngineError).statusCode).toBe(409);

    const serverErr = await client.createContainer({ Image: "fixture/500-on-create" }).catch((e: unknown) => e);
    expect((serverErr as DockerEngineError).kind).toBe("server-error");
    expect((serverErr as DockerEngineError).statusCode).toBe(500);
  });

  it("events() yields NDJSON container lifecycle events for a running container", async () => {
    const created = await client.createContainer({ Image: "alpine:3.20", Cmd: ["true"], Labels: { "fixture.execDelayMs": "20" } });
    await client.startContainer(created.Id);
    const events = await collect(client.events({ type: ["container"] }), 2);
    expect(events.map((e) => e.Action)).toEqual(["start", "die"]);
    expect(events[0]?.Actor?.ID).toBe(created.Id);
  });

  it("runJobContainer() sets Labels['tit.job_id'], matching tit/jobs/runner.py's stop_docker_siblings filter", async () => {
    const { id } = await runJobContainer(client, {
      image: "alpine:3.20",
      cmd: ["true"],
      jobId: "job-abc123",
      mounts: [{ hostPath: "/host/project", containerPath: "/data", readOnly: true }],
      env: { OMP_NUM_THREADS: "4" },
    });
    const inspected = await client.inspectContainer(id);
    expect(inspected.Config.Labels).toMatchObject({ "tit.job_id": "job-abc123" });
    expect(inspected.State.Running).toBe(true);
  });
});
