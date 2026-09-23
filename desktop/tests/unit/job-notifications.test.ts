/**
 * Job-completion notifications (`src/shared/jobNotifications.ts`): the text, the preference
 * filter, and the "transition only, no startup replay" rule. Expected strings are the wording the
 * maintainer specified (2026-09-23), not read back from the formatter. The Electron side (showing
 * the banner, focusing the window on click) is `src/main/jobsNotifier.ts` and is tried by hand.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_NOTIFICATION_PREFS,
  formatJobNotification,
  normalizeNotificationPrefs,
  notificationDecision,
  notificationFailureHint,
  observeTransition,
  SAMPLE_FINISHED_JOB,
  soundPlan,
  TI_SOUNDS,
} from "../../src/shared/jobNotifications";

describe("formatJobNotification", () => {
  const sim = { kind: "sim", state: "succeeded" as const, subject_ids: ["101"], config: { montages: [{ name: "L_Insula" }] } };

  it("minimal is the title alone", () => {
    expect(formatJobNotification(sim, "minimal")).toEqual({ title: "Simulation finished" });
  });

  it("detailed adds subject and montage", () => {
    expect(formatJobNotification(sim, "detailed")).toEqual({ title: "Simulation finished", body: "sub-101 · montage L_Insula" });
  });

  it("names a failure", () => {
    expect(formatJobNotification({ ...sim, state: "failed", config: undefined }, "detailed")).toEqual({ title: "Simulation failed", body: "sub-101" });
  });

  it("names a flex run by its output folder", () => {
    const flex = { kind: "flex", state: "succeeded" as const, subject_ids: ["sub-102"], config: { output_folder: "/mnt/p/derivatives/SimNIBS/sub-102/flex-search/Left-Hippocampus" } };
    expect(formatJobNotification(flex, "detailed")).toEqual({ title: "Flex optimization finished", body: "sub-102 · Left-Hippocampus" });
  });

  it("uses the ROI name for exhaustive search and the region for the analyzer", () => {
    expect(formatJobNotification({ kind: "ex", state: "succeeded", subject_ids: ["101"], config: { roi_name: "L-Insula.csv" } }, "detailed").body).toBe("sub-101 · L-Insula");
    expect(formatJobNotification({ kind: "analyzer", state: "succeeded", subject_ids: ["101"], config: { region: "Left-Hippocampus" } }, "detailed").body).toBe("sub-101 · Left-Hippocampus");
  });

  it("counts many montages and many subjects rather than listing them", () => {
    const job = { kind: "sim", state: "succeeded" as const, subject_ids: ["1", "2", "3"], config: { montages: [{ name: "a" }, { name: "b" }] } };
    expect(formatJobNotification(job, "detailed").body).toBe("3 subjects · 2 montages");
  });

  it("falls back to 'Job' for a kind with no label", () => {
    expect(formatJobNotification({ kind: "new_kind", state: "succeeded", subject_ids: [] }, "detailed")).toEqual({ title: "Job finished" });
  });
});

describe("notificationDecision", () => {
  const on = DEFAULT_NOTIFICATION_PREFS;

  it("shows successes and failures by default, silent banner plus the Pulse", () => {
    expect(notificationDecision(on, "succeeded")).toEqual({ show: true, silent: true, play: "pulse" });
    expect(notificationDecision(on, "failed")).toEqual({ show: true, silent: true, play: "pulse" });
  });

  it("shows nothing when turned off", () => {
    expect(notificationDecision({ ...on, enabled: false }, "failed").show).toBe(false);
  });

  it("failures-only drops successes", () => {
    const failures = { ...on, events: "failures" as const };
    expect(notificationDecision(failures, "succeeded").show).toBe(false);
    expect(notificationDecision(failures, "failed").show).toBe(true);
  });

  it("never shows cancelled jobs", () => {
    expect(notificationDecision(on, "cancelled").show).toBe(false);
  });
});

describe("soundPlan", () => {
  it("system default is the OS sound: an audible banner and nothing played", () => {
    expect(soundPlan("system")).toEqual({ silent: false });
  });

  it("none is a silent banner and nothing played", () => {
    expect(soundPlan("none")).toEqual({ silent: true });
  });

  it("a TI-Toolbox sound is a silent banner plus that sound", () => {
    for (const { id } of TI_SOUNDS) expect(soundPlan(id)).toEqual({ silent: true, play: id });
  });
});

describe("observeTransition", () => {
  it("fires once when a job seen running finishes", () => {
    const seen = new Map<string, string>();
    expect(observeTransition(seen, "j1", "queued")).toBe(false);
    expect(observeTransition(seen, "j1", "running")).toBe(false);
    expect(observeTransition(seen, "j1", "succeeded")).toBe(true);
    expect(observeTransition(seen, "j1", "succeeded")).toBe(false);
  });

  it("never fires for a job first seen already finished (no startup replay)", () => {
    const seen = new Map<string, string>();
    expect(observeTransition(seen, "old", "failed")).toBe(false);
    expect(observeTransition(seen, "old", "failed")).toBe(false);
  });
});

describe("normalizeNotificationPrefs", () => {
  it("defaults to on, detailed, the Pulse, all", () => {
    expect(normalizeNotificationPrefs(undefined)).toEqual({ enabled: true, detail: "detailed", sound: "pulse", events: "all" });
  });

  it("keeps valid fields and repairs invalid ones", () => {
    expect(normalizeNotificationPrefs({ enabled: false, detail: "loud", events: "failures" })).toEqual({ enabled: false, detail: "detailed", sound: "pulse", events: "failures" });
  });

  it("keeps every known sound and rejects an unknown or non-string one", () => {
    for (const sound of ["none", "system", "chime", "pulse", "tick"]) expect(normalizeNotificationPrefs({ sound }).sound).toBe(sound);
    for (const sound of ["gong", "../../etc/passwd", "Pulse", 3, null]) expect(normalizeNotificationPrefs({ sound }).sound).toBe("pulse");
  });

  it("a saved Soft bell or Ripple, both withdrawn on 2026-09-23, becomes the Pulse", () => {
    expect(normalizeNotificationPrefs({ sound: "soft-bell" }).sound).toBe("pulse");
    expect(normalizeNotificationPrefs({ sound: "ripple" }).sound).toBe("pulse");
  });

  it("migrates the old on/off sound: on is the default sound, off is none", () => {
    expect(normalizeNotificationPrefs({ sound: true }).sound).toBe("pulse");
    expect(normalizeNotificationPrefs({ sound: false }).sound).toBe("none");
  });
});

describe("notificationFailureHint", () => {
  // The macOS string is what Electron 44's Notification 'failed' event carried on this Mac
  // (2026-09-23, Darwin 24.6) for the npm Electron.app, read from a probe script — not typed from docs.
  const denied = "The operation couldn’t be completed. (UNErrorDomain error 1.)";

  it("points a dev checkout at Electron's entry and the re-sign script", () => {
    const hint = notificationFailureHint(denied, "darwin", false);
    expect(hint).toContain("System Settings → Notifications");
    expect(hint).toContain("Electron");
    expect(hint).toContain("npm --prefix desktop run sign:dev-electron");
  });

  it("points the packaged app at its own entry", () => {
    expect(notificationFailureHint(denied, "darwin", true)).toBe("Allow TI-Toolbox in System Settings → Notifications.");
  });

  it("gives no macOS hint elsewhere or for an unrelated error", () => {
    expect(notificationFailureHint(denied, "linux", false)).toBeUndefined();
    expect(notificationFailureHint("The system did not confirm the notification.", "darwin", true)).toBeUndefined();
  });
});

describe("test notification sample", () => {
  it("reads like a real finished simulation at both detail levels", () => {
    expect(formatJobNotification(SAMPLE_FINISHED_JOB, "minimal")).toEqual({ title: "Simulation finished" });
    expect(formatJobNotification(SAMPLE_FINISHED_JOB, "detailed")).toEqual({ title: "Simulation finished", body: "sub-ernie · montage test_montage" });
  });
});

describe("shipped sound files", () => {
  // Written by `python3 dev/generate_notification_sounds.py`; the header is read with DataView,
  // not the generator, so a missing, renamed or re-encoded file fails here.
  it("has one short 16-bit mono WAV per TI-Toolbox sound", () => {
    expect(TI_SOUNDS.length).toBeGreaterThan(0);
    for (const { id } of TI_SOUNDS) {
      const bytes = readFileSync(join(__dirname, "../../src/renderer/assets/sounds", `${id}.wav`));
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      expect(bytes.subarray(0, 4).toString()).toBe("RIFF");
      expect(view.getUint16(22, true)).toBe(1); // channels
      expect(view.getUint16(34, true)).toBe(16); // bits per sample
      const seconds = view.getUint32(40, true) / view.getUint32(28, true); // data bytes / byte rate
      expect(seconds).toBeLessThanOrEqual(1);
      // Over Vite's 4 KB inline limit, so it ships as a file the CSP allows, never a data: URI.
      expect(bytes.byteLength).toBeGreaterThan(4096);
    }
  });
});
