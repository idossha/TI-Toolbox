// @vitest-environment jsdom
/**
 * Settings ▸ Notifications: the Sound selector shows the saved choice (an old on/off value
 * migrated), Preview plays the selected TI-Toolbox sound, and Send test notification sends the
 * sample banner silent-plus-sound, audible (system sound) or silent, and says inline whether the
 * OS showed it. Playback is observed at `HTMLMediaElement.play` (jsdom has no audio); the OS side
 * (Electron's show/failed events) is `main/jobsNotifier.ts`, tried by hand.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NotificationsCard } from "../../src/renderer/pages/settings/NotificationsCard";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
const notify = vi.fn();
const played: { src: string; rate: number }[] = [];

function mount(sound: unknown) {
  (window as unknown as { tit: unknown }).tit = {
    getSettings: async () => ({ notifications: { enabled: true, detail: "minimal", sound, events: "all" } }),
    setSettings: vi.fn(),
    notify,
  };
}

beforeEach(() => {
  notify.mockReset();
  played.length = 0;
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    played.push({ src: this.src, rate: this.playbackRate });
    return Promise.resolve();
  });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  delete (window as unknown as { tit?: unknown }).tit;
});

async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <NotificationsCard />
      </QueryClientProvider>,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  for (let i = 0; i < 50 && !button("Send test notification"); i++) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
  }
  expect(button("Send test notification")).toBeDefined();
}

const button = (text: string) => [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(text));
const soundTrigger = () => container.querySelector('[aria-label="Notification sound"]');

async function click(text: string) {
  await act(async () => {
    button(text)!.click();
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  return container.querySelector('[role="status"]')?.textContent ?? "";
}

it("the selector shows the saved sound, and Preview plays it", async () => {
  mount("tick");
  await render();
  expect(soundTrigger()?.textContent).toContain("Tick");
  await click("Preview");
  expect(played).toHaveLength(1);
  expect(played[0]!.src).toContain("tick");
  expect(played[0]!.rate).toBe(1);
});

it("an old sound-off setting reads as None, with Preview disabled and a silent test banner", async () => {
  mount(false);
  await render();
  expect(soundTrigger()?.textContent).toContain("None");
  expect(button("Preview")!.disabled).toBe(true);
  notify.mockResolvedValue({ ok: true });
  expect(await click("Send test notification")).toBe("Shown.");
  expect(notify).toHaveBeenCalledWith("Simulation finished", undefined, true);
  expect(played).toHaveLength(0);
});

it("a TI-Toolbox sound sends the test banner silent and plays the sound", async () => {
  mount("chime");
  await render();
  notify.mockResolvedValue({ ok: true });
  expect(await click("Send test notification")).toBe("Shown.");
  expect(notify).toHaveBeenCalledWith("Simulation finished", undefined, true);
  expect(played.map((p) => p.src)).toEqual([expect.stringContaining("chime")]);
});

it("System default sends an audible test banner and plays nothing itself", async () => {
  mount("system");
  await render();
  expect(soundTrigger()?.textContent).toContain("System default");
  expect(button("Preview")!.disabled).toBe(true);
  notify.mockResolvedValue({ ok: true });
  await click("Send test notification");
  expect(notify).toHaveBeenCalledWith("Simulation finished", undefined, false);
  expect(played).toHaveLength(0);
});

it("reports why it was not shown, with the hint", async () => {
  mount("none");
  await render();
  notify.mockResolvedValue({ ok: false, reason: "denied", hint: "Allow TI-Toolbox in System Settings → Notifications." });
  const status = await click("Send test notification");
  expect(status).toContain("Not shown: denied");
  expect(status).toContain("Allow TI-Toolbox in System Settings → Notifications.");
});

it("the player drops a failure a fourth lower and ignores an unknown id from main", async () => {
  const { playNotificationSound } = await import("../../src/renderer/app/notificationSound");
  playNotificationSound("pulse", true);
  playNotificationSound("../../secret.wav");
  playNotificationSound("system");
  expect(played).toEqual([{ src: expect.stringContaining("pulse"), rate: 0.75 }]);
});
