/**
 * What a finished job's native notification says, and whether it is shown at all.
 *
 * Pure (no Electron), so main (`main/jobsNotifier.ts`, which shows it) and the renderer
 * (Settings ▸ Project ▸ Notifications, which edits the preferences) share one definition, and
 * `tests/unit/job-notifications.test.ts` reads it without a runtime.
 */

export interface NotificationPrefs {
  enabled: boolean;
  /** "minimal": title only ("Simulation finished"); "detailed": adds subject and run/target. */
  detail: "minimal" | "detailed";
  /**
   * "none" and "system" set the native banner's `silent` flag; a TI-Toolbox sound shows it silent
   * and the main window plays the file instead (`renderer/app/notificationSound.ts`).
   */
  sound: NotificationSound;
  events: "all" | "failures";
}

/**
 * The sounds shipped with TI-Toolbox, synthesized by `dev/generate_notification_sounds.py` into
 * `renderer/assets/sounds/<id>.wav`. A failure plays the same sound a fourth lower.
 */
export const TI_SOUNDS = [
  { id: "pulse", label: "Pulse" },
  { id: "chime", label: "Chime" },
  { id: "tick", label: "Tick" },
] as const;
export type TiSoundId = (typeof TI_SOUNDS)[number]["id"];
export type NotificationSound = "none" | "system" | TiSoundId;

export function isTiSound(value: unknown): value is TiSoundId {
  return TI_SOUNDS.some((s) => s.id === value);
}

export function isNotificationSound(value: unknown): value is NotificationSound {
  return value === "none" || value === "system" || isTiSound(value);
}

export const DEFAULT_NOTIFICATION_PREFS: NotificationPrefs = { enabled: true, detail: "detailed", sound: "pulse", events: "all" };

/** The old on/off `sound` (before 2026-09-23) reads as the default sound or none. */
function soundPref(raw: unknown): NotificationSound {
  if (raw === true) return DEFAULT_NOTIFICATION_PREFS.sound;
  if (raw === false) return "none";
  return isNotificationSound(raw) ? raw : DEFAULT_NOTIFICATION_PREFS.sound;
}

/** Whatever `settings.json` holds, as valid preferences; an unknown or missing field takes its default. */
export function normalizeNotificationPrefs(raw: unknown): NotificationPrefs {
  const p = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const d = DEFAULT_NOTIFICATION_PREFS;
  return {
    enabled: typeof p.enabled === "boolean" ? p.enabled : d.enabled,
    detail: p.detail === "minimal" || p.detail === "detailed" ? p.detail : d.detail,
    sound: soundPref(p.sound),
    events: p.events === "all" || p.events === "failures" ? p.events : d.events,
  };
}

/** One human label per job kind. A kind missing here reads as "Job". */
export const JOB_KIND_LABELS: Record<string, string> = {
  pre: "Pre-processing",
  sim: "Simulation",
  flex: "Flex optimization",
  flex_adaptive: "Adaptive flex optimization",
  flex_pareto: "Pareto sweep",
  ex: "Exhaustive search",
  mex: "Multipolar exhaustive search",
  recip: "Reciprocity search",
  leadfield: "Leadfield",
  analyzer: "Analysis",
  stats: "Group statistics",
  source: "Source forward model",
  blender: "3D export",
  nifti_average: "NIfTI averaging",
  nilearn: "Nilearn visuals",
  project_init: "Project setup",
  tools: "Tool",
  report: "Report",
};

export type FinishedState = "succeeded" | "failed";

export interface FinishedJob {
  kind: string;
  state: FinishedState;
  subject_ids: string[];
  /** The job's submitted config (`GET /api/jobs/{id}` → `spec.config`), when it could be read. */
  config?: Record<string, unknown>;
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled", "skipped", "lost"]);

/**
 * The "transition only" rule: true when `state` is a terminal state and this session saw the same
 * job earlier in a non-terminal one. A job first seen already finished (anything the server
 * re-broadcasts about a job that ended before the app attached) never notifies. Records `state`.
 */
export function observeTransition(seen: Map<string, string>, id: string, state: string): boolean {
  const previous = seen.get(id);
  seen.set(id, state);
  return TERMINAL.has(state) && previous !== undefined && !TERMINAL.has(previous);
}

/**
 * How a sound choice reaches the banner: the OS sound (`silent: false`), or a silent banner plus,
 * for a TI-Toolbox sound, the file to play. Used for job banners and the Settings test alike.
 */
export function soundPlan(sound: NotificationSound): { silent: boolean; play?: TiSoundId } {
  if (sound === "system") return { silent: false };
  return sound === "none" ? { silent: true } : { silent: true, play: sound };
}

/**
 * Whether to show a notification for a job that just reached `state`, and how it sounds.
 * Cancelled/skipped/lost jobs stay silent: the user cancelled them, or they ended with the
 * server. The chosen sound plays even while the app is in front: it was picked to be heard.
 */
export function notificationDecision(prefs: NotificationPrefs, state: string): { show: boolean; silent: boolean; play?: TiSoundId } {
  const show = prefs.enabled && (state === "failed" || (state === "succeeded" && prefs.events === "all"));
  return { show, ...soundPlan(prefs.sound) };
}

function subjectsText(ids: string[]): string {
  const named = ids.map((id) => (id.startsWith("sub-") ? id : `sub-${id}`));
  return named.length > 2 ? `${named.length} subjects` : named.join(", ");
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}

function basename(path: unknown): string | undefined {
  return str(typeof path === "string" ? path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() : undefined);
}

/** The run or target a job's config names — montage, ROI, region or output folder — if any. */
export function jobTarget(kind: string, config: Record<string, unknown> | undefined): string | undefined {
  if (!config) return undefined;
  if (kind === "sim" && Array.isArray(config.montages)) {
    const montages = config.montages as Record<string, unknown>[];
    if (montages.length > 1) return `${montages.length} montages`;
    const name = str(montages[0]?.display_name) ?? str(montages[0]?.name);
    return name ? `montage ${name}` : undefined;
  }
  if (kind === "analyzer") {
    const region = Array.isArray(config.region) ? config.region.filter((r) => typeof r === "string").join("+") : str(config.region);
    return str(region) ?? str(config.simulation);
  }
  return str(config.run_name) ?? str(config.roi_name)?.replace(/\.csv$/i, "") ?? basename(config.output_folder);
}

export function formatJobNotification(job: FinishedJob, detail: NotificationPrefs["detail"]): { title: string; body?: string } {
  const label = JOB_KIND_LABELS[job.kind] ?? "Job";
  const title = `${label} ${job.state === "succeeded" ? "finished" : "failed"}`;
  if (detail === "minimal") return { title };
  const parts = [subjectsText(job.subject_ids), jobTarget(job.kind, job.config)].filter((p): p is string => !!p);
  return parts.length ? { title, body: parts.join(" · ") } : { title };
}

/** The Settings card's "Send test notification" banner: a made-up simulation, worded like a real one. */
export const SAMPLE_FINISHED_JOB: FinishedJob = { kind: "sim", state: "succeeded", subject_ids: ["ernie"], config: { montages: [{ name: "test_montage" }] } };

/** What `window.tit.notify` reports: the banner was shown, or why not. */
export type NotifyResult = { ok: true } | { ok: false; reason: string; hint?: string };

/**
 * The one-line fix to show under a failed banner, or undefined when there is none to give.
 * macOS answers `UNErrorDomain error 1` (notifications not allowed) both when the user turned the
 * app off and when the app has no valid code signature: an unsigned bundle is never asked for
 * permission and never listed in System Settings. The Electron.app npm ships is only
 * linker-signed, so a checkout re-signs it ad hoc (`npm run sign:dev-electron`, also run on install).
 */
export function notificationFailureHint(reason: string, platform: string, packaged: boolean): string | undefined {
  if (platform !== "darwin" || !/UNErrorDomain error 1\b|not allowed|denied|unsupported/i.test(reason)) return undefined;
  if (packaged) return "Allow TI-Toolbox in System Settings → Notifications.";
  return "Allow Electron in System Settings → Notifications. Not listed there? Run npm --prefix desktop run sign:dev-electron and relaunch.";
}
