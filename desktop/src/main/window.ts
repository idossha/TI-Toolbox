/**
 * Whether this launch is allowed to put a window, a dock icon or a notification banner on the
 * user's screen.
 *
 * A test run must not hijack the monitor. `npm run e2e` launches Electron once per spec file — 15
 * times today — and every launch used to raise a 1280x820 window, take the keyboard focus off
 * whatever the developer was doing and, under a tiling window manager, re-tile the whole
 * workspace. None of that is what the tests are for: a `BrowserWindow` that is created and never
 * shown still loads the renderer, answers CDP, runs WebGL on the real GPU and screenshots
 * identically, so nothing is lost by keeping it off the screen.
 *
 * Two modes, and the env vars that pick them:
 *
 * | `TIT_E2E_HEADED` | `TIT_E2E_OFFSCREEN` | mode | what happens |
 * |---|---|---|---|
 * | `1` | anything | `'normal'` | a real, shown, focusable window — the debugging opt-in |
 * | unset | `1` | `'offscreen'` | window built and never shown; no dock icon; no notifications |
 * | unset | unset | `'normal'` | a normal user launch, untouched |
 *
 * `TIT_E2E_HEADED` wins, so one variable turns the windows back on for every spec at once.
 * `tests/e2e/_helpers.ts`'s `offscreenEnv()` sets `TIT_E2E_OFFSCREEN=1` by default on darwin;
 * nothing sets it for a user.
 *
 * **Why not a real window parked off-screen.** macOS clamps the frame: a window asked to sit at
 * `x: -10000` comes back on screen, and a tiling window manager then re-tiles it into view.
 * Never shown is the only position nothing can clamp.
 *
 * **Why not Electron's OSR** (`webPreferences.offscreen`). It replaces the compositor with a
 * CPU-side `paint` event, which changes exactly the frame timings and screenshot path that a
 * viewer-hosting app wants measured honestly. A never-shown window keeps the real compositor.
 */

export type WindowMode = "normal" | "offscreen";

export function windowMode(env: NodeJS.ProcessEnv = process.env): WindowMode {
  if (env.TIT_E2E_HEADED === "1") return "normal";
  return env.TIT_E2E_OFFSCREEN === "1" ? "offscreen" : "normal";
}

/**
 * True when this launch may raise UI the window server composites on top of everything: the dock
 * icon and OS notification banners. A job-completion banner is as much a monitor hijack as a
 * window is — it appears over the developer's work — and `jobsNotifier` fires them on a timer, so
 * an offscreen run has to be silent as well as invisible.
 */
export function mayShowSystemUi(mode: WindowMode = windowMode()): boolean {
  return mode === "normal";
}
