/**
 * Plays a TI-Toolbox notification sound (`shared/jobNotifications.ts` `TI_SOUNDS`) in this
 * window. Main has no audio API, so a job banner's sound arrives here as `onNotificationSound`;
 * Settings ▸ Notifications calls it directly for Preview and the test banner. The files are Vite
 * assets (>4 KB, so never inlined as `data:` URIs, which the CSP's `default-src 'self'` would
 * block) and ship in `out/renderer` for dev, packaged and container-served UIs alike. An offscreen
 * test window is muted by main (`setAudioMuted`), so tests stay quiet.
 */
import { isTiSound, type TiSoundId } from "../../shared/jobNotifications";
import chime from "../assets/sounds/chime.wav";
import pulse from "../assets/sounds/pulse.wav";
import tick from "../assets/sounds/tick.wav";

const URLS: Record<TiSoundId, string> = { chime, pulse, tick };

/** A failure plays the same file at 3/4 speed with pitch following: a fourth lower, a bit longer. */
export function playNotificationSound(id: unknown, failed = false): void {
  if (!isTiSound(id)) return;
  const audio = new Audio(URLS[id]);
  if (failed) {
    audio.preservesPitch = false;
    audio.playbackRate = 0.75;
  }
  void audio.play().catch(() => undefined);
}
