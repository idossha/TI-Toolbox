/**
 * LIVE verification driver — N0.3 spike gate step 4. Talks to the real Docker Desktop (or any
 * Docker Engine API-compatible daemon) over its real socket, using the actual
 * DockerEngineClient/discover code from desktop/src/main/docker/ (copied into a scratch build
 * dir by run-live-verify.sh and compiled to CommonJS so plain `node` can run it without adopting
 * the repo's own bundler-style extension-less import convention at runtime).
 *
 * Run via ./run-live-verify.sh from this directory. Requires a real, running Docker engine —
 * this is a live-infrastructure check, not part of the hermetic vitest/pytest gates.
 */
import { discover } from "./docker/discover";
import { DockerEngineClient, runJobContainer, type DockerConnection } from "./docker/engine";

function log(...args: unknown[]): void {
  // eslint-disable-next-line no-console
  console.log(...args);
}

async function main(): Promise<void> {
  log("=== 1. discover() ===");
  const result = await discover();
  if (!result.available) {
    log("NOT AVAILABLE:", result.kind, result.message);
    process.exit(1);
  }
  log("connection:", JSON.stringify(result.connection), "source:", result.source);
  const conn: DockerConnection = result.connection;

  const client = new DockerEngineClient(conn, { timeoutMs: 20_000 });

  log("\n=== 2. version() / info() ===");
  const version = await client.version();
  log("version:", JSON.stringify(version));
  const info = await client.info();
  log("info: ServerVersion=%s OSType=%s NCPU=%s MemTotal=%s", info.ServerVersion, info.OSType, info.NCPU, info.MemTotal);

  log("\n=== 3. pullImage(alpine:3.20) with progress ===");
  let progressCount = 0;
  let firstProgressLine: string | null = null;
  let maxTotalBytesSeen = 0;
  const startPull = Date.now();
  await client.pullImage("alpine", "3.20", (e) => {
    progressCount++;
    const line = JSON.stringify(e);
    if (firstProgressLine === null) firstProgressLine = line;
    if (e.progressDetail?.total) maxTotalBytesSeen = Math.max(maxTotalBytesSeen, e.progressDetail.total);
  });
  log("pull done in", Date.now() - startPull, "ms; progress events:", progressCount, "; max total bytes seen in one progressDetail:", maxTotalBytesSeen);
  log("first progress line:", firstProgressLine);

  log("\n=== 4. createContainer + startContainer ===");
  const created = await client.createContainer({
    Image: "alpine:3.20",
    Cmd: ["sh", "-c", "echo out; echo err 1>&2; sleep 1; exit 3"],
    Tty: false,
    Labels: { "tit.job_id": "live-verify-job", "tit.spike": "n0.3" },
  });
  log("created container id:", created.Id);
  await client.startContainer(created.Id);
  log("started.");

  log("\n=== 5. events() (background) ===");
  // Only 2 lifecycle events (start, die) occur before removeContainer() at the very end of this
  // script — a 3rd ("destroy") would only ever arrive after that, so this deliberately only
  // waits for 2, with a hard deadline as a second guard against a genuinely missed event.
  const eventsSeen: string[] = [];
  const eventsPromise = (async () => {
    for await (const evt of client.events({ container: [created.Id] })) {
      eventsSeen.push(`${evt.Type}/${evt.Action}`);
      if (eventsSeen.length >= 2) break;
    }
  })();
  const eventsDeadline = new Promise<void>((resolve) => setTimeout(resolve, 5000));

  log("\n=== 6. logs() demuxed, raw first bytes ===");
  let rawFirstBytesHex = "";
  let sawStdout = "";
  let sawStderr = "";
  // Race the log stream against a hard deadline so a live-container quirk can't hang the spike.
  const logsDeadline = new Promise<void>((resolve) => setTimeout(resolve, 8000));
  const logsWork = (async () => {
    for await (const frame of client.logs(created.Id, { follow: true })) {
      if (rawFirstBytesHex === "") rawFirstBytesHex = Buffer.concat([Buffer.from([frame.stream === "stdout" ? 1 : 2, 0, 0, 0]), frame.payload]).subarray(0, 16).toString("hex");
      if (frame.stream === "stdout") sawStdout += frame.payload.toString("utf8");
      else sawStderr += frame.payload.toString("utf8");
    }
  })();
  await Promise.race([logsWork, logsDeadline]);
  log("stdout:", JSON.stringify(sawStdout));
  log("stderr:", JSON.stringify(sawStderr));
  log("raw first ~16 bytes of a reconstructed frame (hex):", rawFirstBytesHex);

  log("\n=== 7. waitContainer() ===");
  const waitResult = await client.waitContainer(created.Id);
  log("exit code:", waitResult.StatusCode);

  await Promise.race([eventsPromise, eventsDeadline]).catch(() => undefined);
  log("events observed:", JSON.stringify(eventsSeen));

  log("\n=== 8. inspectContainer() after exit ===");
  const inspected = await client.inspectContainer(created.Id);
  log("State:", JSON.stringify(inspected.State));

  log("\n=== 9. removeContainer() ===");
  await client.removeContainer(created.Id);
  log("removed.");

  log("\n=== 10. runJobContainer() convenience wrapper ===");
  const { id: jobContainerId } = await runJobContainer(client, {
    image: "alpine:3.20",
    cmd: ["sleep", "1"],
    jobId: "live-verify-run-job",
    autoRemove: false,
  });
  log("runJobContainer id:", jobContainerId);
  const jobInspect = await client.inspectContainer(jobContainerId);
  log("Labels:", JSON.stringify(jobInspect.Config.Labels));
  await client.waitContainer(jobContainerId);
  await client.removeContainer(jobContainerId);
  log("runJobContainer removed.");

  log("\n=== DONE ===");
  process.exit(waitResult.StatusCode === 3 ? 0 : 2);
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("LIVE VERIFY FAILED:", err);
  process.exit(1);
});
