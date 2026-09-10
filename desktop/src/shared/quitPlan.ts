/**
 * What quitting does when this app owns a backend and jobs are still running.
 *
 * Split out of `main/index.ts` for the same reason as `shared/quitGate.ts`: it has no Electron
 * dependency, so it can be unit-tested with a fake dialog, a fake jobs API and a fake runtime
 * (`main/**` is outside `tsconfig.web.json`, which is what `tests/unit/**` type-checks under).
 *
 * The bug this shape exists to prevent (audit UI-04): the running-jobs question was asked only
 * on the Docker branch. With the bundled native runtime the quit path fell straight through to
 * `nativeRuntime.stop()`, which SIGTERMs the process group and SIGKILLs 1.5 s later — so Cmd+Q
 * during a FEM run killed it with no warning and no chance to cancel cleanly. The question is
 * now asked for EVERY backend this app owns, and the chosen "stop" branch cancels the jobs and
 * waits (bounded) for the server to acknowledge before the runtime is torn down.
 */

/** Only queued/running jobs can be interrupted; skipped/lost are terminal too. */
export function activeJobIds(jobs: unknown): string[] {
  if (!Array.isArray(jobs)) throw new Error("Invalid jobs response");
  const ids: string[] = [];
  for (const job of jobs) {
    if (!job || typeof job !== "object" || typeof job.state !== "string" || typeof job.id !== "string") {
      throw new Error("Invalid job in jobs response");
    }
    if (job.state === "running" || job.state === "queued") ids.push(job.id);
  }
  return ids;
}

export interface QuitBackends {
  /** This app started the Docker stack (something a later launch could reattach to). */
  docker: boolean;
  /** This app spawned the bundled native runtime (nothing survives the quit). */
  native: boolean;
}

export interface QuitDialog {
  buttons: string[];
  message: string;
  detail: string;
  defaultId: number;
  cancelId: number;
}

export interface QuitPlanDeps {
  /** Ids of the jobs the server currently reports as running. */
  listRunningJobs: () => Promise<string[]>;
  /** Show the question; resolves with the index of the button pressed. */
  confirm: (dialog: QuitDialog) => Promise<number>;
  /** `POST /api/jobs/{id}/cancel`, best effort. */
  cancelJob: (id: string) => Promise<void>;
  /** Stop the Docker stack this app started. */
  stopDocker: () => Promise<void>;
  /** Stop the native runtime this app spawned. */
  stopNative: () => Promise<void>;
  /** Injected so the ack wait is instant under fake timers. */
  sleep: (ms: number) => Promise<void>;
  now: () => number;
}

/** How long the quit waits for cancelled jobs to actually leave the running list. */
export const CANCEL_ACK_TIMEOUT_MS = 5000;
const CANCEL_POLL_MS = 200;

function plural(n: number): string {
  return `${n} active job${n === 1 ? "" : "s"} (running or queued)`;
}

/**
 * Decide and carry out what happens on quit. Resolves true when the app may go away, false when
 * the user cancelled and the app must stay up.
 */
export async function runQuitPlan(backends: QuitBackends, deps: QuitPlanDeps): Promise<boolean> {
  if (!backends.docker && !backends.native) return true;

  let running: string[];
  try {
    running = await deps.listRunningJobs();
  } catch {
    // A crashed server cannot report jobs, but the user must still be able to close its runtime.
    const choice = await deps.confirm({
      buttons: ["Cancel", "Stop jobs and quit"],
      message: "Job status is unavailable",
      detail: "The server could not report its jobs. Closing stops its runtime and interrupts any running or queued jobs. Project files and named volumes are preserved.",
      defaultId: 0, cancelId: 0,
    });
    if (choice !== 1) return false;
    running = [];
  }

  if (running.length > 0) {
    const choice = await deps.confirm({
      buttons: ["Cancel", "Stop jobs and quit"], message: plural(running.length),
      detail: "Closing the app stops its container and cancels running and queued jobs. Project files and named volumes are preserved.",
      defaultId: 0, cancelId: 0,
    });
    if (choice !== 1) return false;
    await cancelAndWait(running, deps);
  }
  if (backends.docker) await deps.stopDocker();
  if (backends.native) await deps.stopNative();
  return true;
}

/**
 * Ask the server to cancel each job, then wait for it to say they are gone.
 *
 * Bounded: an unresponsive server must not make the app unquittable, so after
 * `CANCEL_ACK_TIMEOUT_MS` the teardown proceeds anyway (which is what the pre-existing SIGTERM/
 * SIGKILL pair is there for).
 */
async function cancelAndWait(ids: string[], deps: QuitPlanDeps): Promise<void> {
  await Promise.all(ids.map((id) => deps.cancelJob(id).catch(() => undefined)));
  const deadline = deps.now() + CANCEL_ACK_TIMEOUT_MS;
  const pending = new Set(ids);
  for (;;) {
    let still: string[];
    try {
      still = await deps.listRunningJobs();
    } catch {
      return;
    }
    if (!still.some((id) => pending.has(id))) return;
    if (deps.now() >= deadline) return;
    await deps.sleep(CANCEL_POLL_MS);
  }
}
