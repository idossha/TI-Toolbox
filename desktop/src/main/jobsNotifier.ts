/**
 * Desktop notification on job completion: the main process (not the renderer) listens on
 * `/ws/jobs` for the currently-attached stack and fires a native `Notification` when a job it saw
 * queued or running reaches `succeeded`/`failed` — never for a job that had already finished
 * before the app attached. Wording, preferences and the transition rule live in
 * `shared/jobNotifications.ts`; the preferences are read from `settings.json` at each show, so a
 * change in Settings applies to the next job without reconnecting. Uses the runtime's global `WebSocket` (Node 22+,
 * bundled by Electron 44) rather than an npm dependency — the main process has no dependency-free
 * requirement (that is a preload-only rule) but `ws` is a devDependency owned by another lane's
 * `package.json`, so this stays off it entirely.
 */
import { app, Notification, net, type BrowserWindow } from "electron";
import { formatJobNotification, normalizeNotificationPrefs, notificationDecision, notificationFailureHint, observeTransition, type FinishedState, type NotifyResult } from "../shared/jobNotifications";
import { log } from "./log";
import { readSettings } from "./settings";
import { mayShowSystemUi } from "./window";

interface JobsWsMessage {
  type?: string;
  job?: { id?: string; state?: string; kind?: string; subject_ids?: string[] };
}

let socket: WebSocket | null = null;
const notified = new Set<string>();
/** Last state seen per job this session — the "transition only" rule's memory. */
const seen = new Map<string, string>();
/** Shown notifications, held until dismissed so the click handler is not garbage-collected. */
const shown = new Set<Notification>();

/**
 * What else a finished job triggers. The notifier owns the one `/ws/jobs` connection main has, so
 * anything that must happen when a job ends hangs off it rather than opening a second socket.
 * Today that is the host-side Tetravox pass over the job's ROI plates (`roiPlates.ts`).
 */
type JobFinishedListener = (jobId: string, state: "succeeded" | "failed") => void;
let onJobFinished: JobFinishedListener | undefined;

export function setJobFinishedListener(listener?: JobFinishedListener): void {
  onJobFinished = listener;
}

export function stopNotifyingJobCompletions(): void {
  try {
    socket?.close();
  } catch {
    // Already closing/closed.
  }
  socket = null;
  notified.clear();
  seen.clear();
}

async function jobConfig(origin: string, token: string, jobId: string): Promise<Record<string, unknown> | undefined> {
  try {
    const res = await net.fetch(`${origin}/api/jobs/${encodeURIComponent(jobId)}`, { headers: { authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(5000) });
    if (!res.ok) return undefined;
    const detail = (await res.json()) as { spec?: { config?: Record<string, unknown> } };
    return detail.spec?.config;
  } catch {
    return undefined;
  }
}

/**
 * Show one native banner and resolve with what the OS said: Electron's `show` event, or `failed`
 * with the OS error (macOS: `UNErrorDomain error 1` when the app is not allowed — including an
 * unsigned dev Electron.app, which macOS never lists; see `notificationFailureHint`). Without the
 * `failed` listener that error is swallowed and a missing banner leaves no trace.
 */
export function showNativeNotification(options: { title: string; body?: string; silent?: boolean }, win?: BrowserWindow): Promise<NotifyResult> {
  const fail = (reason: string): NotifyResult => ({ ok: false, reason, hint: notificationFailureHint(reason, process.platform, app.isPackaged) });
  if (!Notification.isSupported()) return Promise.resolve(fail("Notifications are unsupported on this system."));
  if (!mayShowSystemUi()) return Promise.resolve({ ok: false, reason: "Notifications are off in an offscreen test run." });
  return new Promise((resolve) => {
    const notification = new Notification(options);
    let settled = false;
    const settle = (result: NotifyResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (!result.ok) log("warn", `notification "${options.title}" failed: ${result.reason}`);
      resolve(result);
    };
    const timer = setTimeout(() => settle(fail("The system did not confirm the notification.")), 5000);
    shown.add(notification);
    notification.on("show", () => settle({ ok: true }));
    notification.on("failed", (_e, error) => {
      shown.delete(notification);
      settle(fail(String(error)));
    });
    notification.on("close", () => shown.delete(notification));
    notification.on("click", () => {
      shown.delete(notification);
      if (!win || win.isDestroyed()) return;
      if (win.isMinimized()) win.restore();
      win.show();
      win.focus();
    });
    notification.show();
  });
}

async function showJobNotification(origin: string, token: string, win: BrowserWindow | undefined, job: { id: string; kind: string; state: FinishedState; subject_ids: string[] }): Promise<void> {
  const prefs = normalizeNotificationPrefs(readSettings().notifications);
  const decision = notificationDecision(prefs, job.state);
  if (!decision.show) {
    log("info", `job ${job.id} ${job.state}: no notification (${prefs.enabled ? "failures only" : "turned off"} in Settings)`);
    return;
  }
  const config = prefs.detail === "detailed" ? await jobConfig(origin, token, job.id) : undefined;
  const text = formatJobNotification({ ...job, config }, prefs.detail);
  const result = await showNativeNotification({ ...text, silent: decision.silent }, win);
  if (result.ok) log("info", `job ${job.id} ${job.state}: notification shown`);
  // A TI-Toolbox sound plays in the main window (main has no audio API), even when the banner was
  // refused by the OS: the sound is still the user's cue. Never in an offscreen test run.
  if (decision.play && mayShowSystemUi() && win && !win.isDestroyed()) win.webContents.send("tit:notificationSound", decision.play, job.state === "failed");
}

/** `win` is focused when a notification is clicked, and plays a TI-Toolbox sound. */
export function notifyJobCompletions(origin: string, token: string, win?: BrowserWindow): void {
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
    ws.addEventListener("open", () => log("info", `jobs notifier: listening on ${origin}/ws/jobs`));
    ws.addEventListener("message", (ev: MessageEvent) => {
      let data: JobsWsMessage;
      try {
        data = JSON.parse(String(ev.data)) as JobsWsMessage;
      } catch {
        return;
      }
      const job = data.job;
      if (data.type !== "job" || !job?.id || !job.state) return;
      const finishedLive = observeTransition(seen, job.id, job.state);
      if (job.state !== "succeeded" && job.state !== "failed") return;
      if (notified.has(job.id)) return;
      notified.add(job.id);
      try {
        onJobFinished?.(job.id, job.state as "succeeded" | "failed");
      } catch (err) {
        log("warn", `job-finished listener threw: ${err instanceof Error ? err.message : String(err)}`);
      }
      if (!finishedLive) log("info", `job ${job.id} ${job.state}: no notification (not seen running this session)`);
      else {
        const finished = { id: job.id, kind: job.kind ?? "", state: job.state as FinishedState, subject_ids: job.subject_ids ?? [] };
        void showJobNotification(origin, token, win, finished).catch((err: unknown) => log("warn", `job notification failed: ${err instanceof Error ? err.message : String(err)}`));
      }
    });
    ws.addEventListener("error", () => log("warn", "jobs notifier: WebSocket error"));
    ws.addEventListener("close", (ev: CloseEvent) => {
      log("info", `jobs notifier: socket closed (${ev.code})`);
      if (socket === ws) socket = null;
    });
  } catch (err) {
    log("warn", `jobs notifier failed to connect: ${err instanceof Error ? err.message : String(err)}`);
  }
}
