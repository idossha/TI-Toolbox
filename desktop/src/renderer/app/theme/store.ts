/**
 * Theme setting (DESIGN.md §7, program U9): **light by default**, dark and system available,
 * persisted in localStorage and stamped onto `<html data-theme>`. `initTheme()` must run before
 * React's first render — see `main.tsx` — so the persisted choice never flashes the wrong palette.
 *
 * A first launch with no stored preference renders LIGHT, on a machine set to dark included. Dark
 * is a choice, not an inheritance: every screenshot in DESIGN.md and every acceptance number in
 * §12.3 was read on the light palette, and a v2 build that inherited the OS setting made "the
 * default screen" mean two different pictures depending on whose Mac took it. `system` remains a
 * setting a user can pick (Settings ▸ Appearance, ⌘K "Theme: system"); it is no longer the default.
 */
import { create } from "zustand";

export type ThemeSetting = "system" | "light" | "dark";

const STORAGE_KEY = "tit-theme";

/** The setting a machine with no stored preference gets (U9). */
export const DEFAULT_THEME: ThemeSetting = "light";

function readStored(): ThemeSetting {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    // localStorage unavailable (private mode, sandboxed webview) — fall back to the default.
  }
  return DEFAULT_THEME;
}

function stamp(theme: ThemeSetting): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

interface ThemeStoreState {
  theme: ThemeSetting;
  setTheme: (theme: ThemeSetting) => void;
}

export const useThemeStore = create<ThemeStoreState>((set) => ({
  theme: readStored(),
  setTheme: (theme) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // best-effort persistence only
    }
    stamp(theme);
    set({ theme });
  },
}));

/** Call once, synchronously, before the renderer's first paint. */
export function initTheme(): void {
  stamp(useThemeStore.getState().theme);
}
