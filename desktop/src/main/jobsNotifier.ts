/**
 * Desktop notification on job completion: the main process (not the renderer) listens on
 * `/ws/jobs` for the currently-attached stack and fires a native `Notification` the first time a
 * job reaches `succeeded`/`failed` (TODO §2.9). Uses the runtime's global `WebSocket` (Node 22+,
 * bundled by Electron 44) rather than an npm dependency — the main process has no dependency-free
 * requirement (that is a preload-only rule) but `ws` is a devDependency owned by another lane's
 * `package.json`, so this stays off it entirely.
 */
import { Notification } from "electron";
import { log } from "./log";

interface JobsWsMessage {
  type?: string;
  job?: { id?: string; state?: string; kind?: string };
}

let socket: WebSocket | null = null;
const notified = new Set<string>();

export function stopNotifyingJobCompletions(): void {
  try {
    socket?.close();
  } catch {
    // Already closing/closed.
  }
  socket = null;
  notified.clear();
}

export function notifyJobCompletions(origin: string, token: string): void {
  stopNotifyingJobCompletions();
  // The E2E fake container (`tests/e2e/fixtures/fake-engine-api.mjs`'s in-process tit.server)
  // doesn't implement a `/ws/jobs` upgrade; without this, every connect() in those tests leaves a
  // WebSocket parked in CONNECTING against a plain HTTP response, which does eventually error out —
  // but real dev-machine contention was enough to turn that into flaky multi-minute
  // worker-teardown timeouts.
  if (process.env.TIT_SKIP_JOB_NOTIFICATIONS) return;
  if (typeof WebSocket === "undefined") {
    log("warn", "job-completion notifications unavailable: no global WebSocket in this runtime");
    return;
  }
  const wsUrl = origin.replace(/^http/, "ws") + `/ws/jobs?token=${encodeURIComponent(token)}`;
  try {
    const ws = new WebSocket(wsUrl);
    socket = ws;
    ws.addEventListener("message", (ev: MessageEvent) => {
      let data: JobsWsMessage;
      try {
        data = JSON.parse(String(ev.data)) as JobsWsMessage;
      } catch {
        return;
      }
      const job = data.job;
      if (data.type !== "job" || !job?.id || !job.state) return;
      if (job.state !== "succeeded" && job.state !== "failed") return;
      if (notified.has(job.id)) return;
      notified.add(job.id);
      if (Notification.isSupported()) {
        new Notification({
          title: job.state === "succeeded" ? "Job finished" : "Job failed",
          body: job.kind ? `${job.kind} — ${job.id}` : job.id,
        }).show();
      }
    });
    ws.addEventListener("error", () => log("warn", "jobs notifier: WebSocket error"));
    ws.addEventListener("close", () => {
      if (socket === ws) socket = null;
    });
  } catch (err) {
    log("warn", `jobs notifier failed to connect: ${err instanceof Error ? err.message : String(err)}`);
  }
}
