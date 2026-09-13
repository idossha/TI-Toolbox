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
    await expect(run(request)).resolves.toEqual({ ok: true });
  });
});
