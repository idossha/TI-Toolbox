/**
 * The quit decision (audit UI-04): every backend this app owns asks about running jobs, and the
 * "stop" answer cancels them and waits for the server to acknowledge before the runtime dies.
 */
import { describe, expect, it, vi } from "vitest";
import { runQuitPlan, type QuitDialog, type QuitPlanDeps } from "../../src/shared/quitPlan";

function deps(overrides: Partial<QuitPlanDeps> = {}): QuitPlanDeps & { dialogs: QuitDialog[] } {
  const dialogs: QuitDialog[] = [];
  const base: QuitPlanDeps = {
    listRunningJobs: vi.fn().mockResolvedValue([]),
    confirm: vi.fn(async (dialog: QuitDialog) => {
      dialogs.push(dialog);
      return 0;
    }),
    cancelJob: vi.fn().mockResolvedValue(undefined),
    stopDocker: vi.fn().mockResolvedValue(undefined),
    stopNative: vi.fn().mockResolvedValue(undefined),
    noteStackLeftRunning: vi.fn(),
    sleep: vi.fn().mockResolvedValue(undefined),
    now: () => 0,
    ...overrides,
  };
  const wrapped = {
    ...base,
    confirm: async (dialog: QuitDialog) => {
      dialogs.push(dialog);
      return base.confirm(dialog);
    },
    dialogs,
  };
  return wrapped;
}

describe("runQuitPlan — the native runtime warns about running jobs too (UI-04)", () => {
  it("asks before killing the native runtime out from under a running job", async () => {
    const d = deps({ listRunningJobs: vi.fn().mockResolvedValue(["j1"]), confirm: vi.fn().mockResolvedValue(0) });
    const proceed = await runQuitPlan({ docker: false, native: true }, d);
    expect(d.dialogs).toHaveLength(1);
    expect(proceed).toBe(false); // Cancel is button 0 here
    expect(d.stopNative).not.toHaveBeenCalled();
    expect(d.cancelJob).not.toHaveBeenCalled();
  });

  it('"Stop jobs and quit" cancels every running job and waits for the acknowledgement', async () => {
    const listRunningJobs = vi
      .fn()
      .mockResolvedValueOnce(["j1", "j2"]) // the pre-dialog check
      .mockResolvedValueOnce(["j1"]) // cancel not acknowledged yet
      .mockResolvedValue([]); // gone
    const order: string[] = [];
    const d = deps({
      listRunningJobs,
      confirm: vi.fn().mockResolvedValue(1),
      cancelJob: vi.fn(async (id: string) => {
        order.push(`cancel:${id}`);
      }),
      stopNative: vi.fn(async () => {
        order.push("stopNative");
      }),
    });
    const proceed = await runQuitPlan({ docker: false, native: true }, d);
    expect(proceed).toBe(true);
    expect(d.cancelJob).toHaveBeenCalledTimes(2);
    expect(order[order.length - 1]).toBe("stopNative"); // cancels first, teardown last
    expect(d.sleep).toHaveBeenCalled(); // it actually waited for the ack
  });

  it("stops waiting for the acknowledgement rather than making the app unquittable", async () => {
    let clock = 0;
    const d = deps({
      listRunningJobs: vi.fn().mockResolvedValue(["j1"]),
      confirm: vi.fn().mockResolvedValue(1),
      sleep: vi.fn(async () => {
        clock += 200;
      }),
      now: () => clock,
    });
    const proceed = await runQuitPlan({ docker: false, native: true }, d);
    expect(proceed).toBe(true);
    expect(d.stopNative).toHaveBeenCalled();
  });

  it("with nothing running, quits straight through and still stops the runtime", async () => {
    const d = deps();
    expect(await runQuitPlan({ docker: false, native: true }, d)).toBe(true);
    expect(d.dialogs).toHaveLength(0);
    expect(d.stopNative).toHaveBeenCalled();
  });

  it("owns no backend: no question, nothing stopped", async () => {
    const d = deps({ listRunningJobs: vi.fn().mockResolvedValue(["j1"]) });
    expect(await runQuitPlan({ docker: false, native: false }, d)).toBe(true);
    expect(d.listRunningJobs).not.toHaveBeenCalled();
    expect(d.dialogs).toHaveLength(0);
  });
});

describe("runQuitPlan — the Docker branch keeps its three answers", () => {
  it("Cancel keeps the app up", async () => {
    const d = deps({ listRunningJobs: vi.fn().mockResolvedValue(["j1"]), confirm: vi.fn().mockResolvedValue(2) });
    expect(await runQuitPlan({ docker: true, native: false }, d)).toBe(false);
    expect(d.stopDocker).not.toHaveBeenCalled();
  });

  it("keeping the containers running leaves the jobs alone", async () => {
    const d = deps({ listRunningJobs: vi.fn().mockResolvedValue(["j1"]), confirm: vi.fn().mockResolvedValue(0) });
    expect(await runQuitPlan({ docker: true, native: false }, d)).toBe(true);
    expect(d.cancelJob).not.toHaveBeenCalled();
    expect(d.stopDocker).not.toHaveBeenCalled();
  });

  it("stopping the containers cancels the jobs first", async () => {
    const listRunningJobs = vi.fn().mockResolvedValueOnce(["j1"]).mockResolvedValue([]);
    const d = deps({ listRunningJobs, confirm: vi.fn().mockResolvedValue(1) });
    expect(await runQuitPlan({ docker: true, native: false }, d)).toBe(true);
    expect(d.cancelJob).toHaveBeenCalledWith("j1");
    expect(d.stopDocker).toHaveBeenCalled();
  });

  it("nothing running: the containers are left up and the user is told", async () => {
    const d = deps();
    expect(await runQuitPlan({ docker: true, native: false }, d)).toBe(true);
    expect(d.noteStackLeftRunning).toHaveBeenCalled();
  });
});
