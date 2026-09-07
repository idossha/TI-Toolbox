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
  /** Tell the user the containers were deliberately left up. */
  noteStackLeftRunning: () => void;
  /** Injected so the ack wait is instant under fake timers. */
  sleep: (ms: number) => Promise<void>;
  now: () => number;
}

/** How long the quit waits for cancelled jobs to actually leave the running list. */
export const CANCEL_ACK_TIMEOUT_MS = 5000;
const CANCEL_POLL_MS = 200;

function plural(n: number): string {
  return `${n} job${n === 1 ? "" : "s"} still running`;
}

/**
 * Decide and carry out what happens on quit. Resolves true when the app may go away, false when
 * the user cancelled and the app must stay up.
 */
export async function runQuitPlan(backends: QuitBackends, deps: QuitPlanDeps): Promise<boolean> {
  if (!backends.docker && !backends.native) return true;

  const running = await deps.listRunningJobs();

  if (running.length === 0) {
    if (backends.docker) deps.noteStackLeftRunning();
    if (backends.native) await deps.stopNative();
    return true;
  }

  // Docker keeps its three-way question: leaving containers up is a real option there, because a
  // later launch reattaches to them and the jobs simply keep running. The native runtime has no
  // such option — nothing survives this process — so its question is the two honest answers.
  const dialog: QuitDialog = backends.docker
    ? {
        buttons: ["Keep running in the background", "Stop containers and quit", "Cancel"],
        message: plural(running.length),
        detail:
          "Keep the Docker containers running in the background and reopen the app later, or stop everything now.",
        defaultId: 0,
        cancelId: 2,
      }
    : {
        buttons: ["Cancel", "Stop jobs and quit"],
        message: plural(running.length),
        detail:
          "TI-Toolbox is running these jobs itself, so quitting ends them — nothing keeps running in the background. They will be cancelled before the app closes.",
        defaultId: 0,
        cancelId: 0,
      };
  const choice = await deps.confirm(dialog);

  if (backends.docker) {
    if (choice === 2) return false; // Cancel — do not quit.
    if (choice === 1) {
      await cancelAndWait(running, deps);
      await deps.stopDocker();
    }
  } else if (choice !== 1) {
    return false; // Cancel — do not quit.
  } else {
    await cancelAndWait(running, deps);
  }

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
