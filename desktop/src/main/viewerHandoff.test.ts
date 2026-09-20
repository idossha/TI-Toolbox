import { describe, expect, it, vi } from "vitest";
import { createViewerHandoff } from "./viewerHandoff";

describe("native scene replacement consent", () => {
  it("cancelling preserves the existing window and launches nothing", async () => {
    const launch = vi.fn();
    const confirm = vi.fn(async () => false);
    expect(await createViewerHandoff()({ hasScene: true, running: async () => true, confirm, launch })).toEqual({ ok: false, cancelled: true });
    expect(confirm).toHaveBeenCalledOnce();
    expect(launch).not.toHaveBeenCalled();
  });
  it.each([false, true])("blank launch only focuses, running=%s", async (running) => {
    const confirm = vi.fn(); const launch = vi.fn();
    await createViewerHandoff()({ hasScene: false, running: async () => running, confirm, launch });
    expect(confirm).not.toHaveBeenCalled(); expect(launch).toHaveBeenCalledOnce();
  });
  it("new instance opens directly; existing instance requires consent", async () => {
    const launch = vi.fn(); const confirm = vi.fn(async () => true);
    const run = createViewerHandoff();
    await run({ hasScene: true, running: async () => false, confirm, launch });
    expect(confirm).not.toHaveBeenCalled();
    await run({ hasScene: true, running: async () => true, confirm, launch });
    expect(confirm).toHaveBeenCalledOnce(); expect(launch).toHaveBeenCalledTimes(2);
  });
  it("queued requests recheck running state after the first launch", async () => {
    let running = false;
    const events: string[] = [];
    const run = createViewerHandoff();
    const request = { hasScene: true, running: async () => running, confirm: async () => { events.push("confirm"); return true; }, launch: async () => { events.push("launch"); running = true; } };
    await Promise.all([run(request), run(request)]);
    expect(events).toEqual(["launch", "confirm", "launch"]);
  });
  it("a failed launch does not block later retries", async () => {
    const run = createViewerHandoff(); const launch = vi.fn().mockRejectedValueOnce(new Error("failed")).mockResolvedValue(undefined);
    const request = { hasScene: true, running: async () => false, confirm: async () => true, launch };
    await expect(run(request)).rejects.toThrow("failed");
    await expect(run(request)).resolves.toEqual({ ok: true, status: "launch-requested" });
  });
});


describe("native handoff uncertainty and queue recovery", () => {
  it("an unavailable process probe requires consent and cancellation does not launch", async () => {
    const launch = vi.fn();
    const confirm = vi.fn(async () => false);
    const result = await createViewerHandoff()({
      hasScene: true, running: async () => { throw new Error("process listing denied"); }, confirm, launch,
    });
    expect(result).toEqual({ ok: false, cancelled: true });
    expect(confirm).toHaveBeenCalledOnce();
    expect(launch).not.toHaveBeenCalled();
  });

  it("a blank focus request does not depend on process discovery", async () => {
    const running = vi.fn(async () => { throw new Error("unavailable"); });
    const launch = vi.fn(async () => undefined);
    expect(await createViewerHandoff()({ hasScene: false, running, confirm: async () => false, launch }))
      .toEqual({ ok: true, status: "launch-requested" });
    expect(running).not.toHaveBeenCalled();
    expect(launch).toHaveBeenCalledOnce();
  });

  it("holds the next request until the first launch settles", async () => {
    let finishLaunch!: () => void;
    const pendingLaunch = new Promise<void>((resolve) => { finishLaunch = resolve; });
    let started!: () => void;
    const launchStarted = new Promise<void>((resolve) => { started = resolve; });
    const run = createViewerHandoff();
    const first = run({ hasScene: false, running: async () => false, confirm: async () => true,
      launch: async () => { started(); await pendingLaunch; } });
    await launchStarted;
    const running = vi.fn(async () => true);
    const confirm = vi.fn(async () => false);
    const launch = vi.fn();
    const second = run({ hasScene: true, running, confirm, launch });
    await Promise.resolve();
    expect(running).not.toHaveBeenCalled();
    finishLaunch();
    await first;
    expect(await second).toEqual({ ok: false, cancelled: true });
    expect(confirm).toHaveBeenCalledOnce();
    expect(launch).not.toHaveBeenCalled();
  });

  it("a rejected dialog releases the queue without launching that request", async () => {
    const run = createViewerHandoff();
    const launch = vi.fn(async () => undefined);
    await expect(run({ hasScene: true, running: async () => true,
      confirm: async () => { throw new Error("window closed"); }, launch })).rejects.toThrow("window closed");
    expect(launch).not.toHaveBeenCalled();
    await expect(run({ hasScene: false, running: async () => false, confirm: async () => true, launch }))
      .resolves.toEqual({ ok: true, status: "launch-requested" });
  });
});
