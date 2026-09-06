/**
 * The scene's colours, as numbers.
 *
 * A shader cannot read a CSS custom property, so the palette is numeric here rather than pulled
 * from `ui/tokens.css` at runtime — and it is deliberately ONE palette, not two. The canvas ground
 * is `--canvas: #0b0d10`, which `tokens.css` defines identically in light and dark (a 3D pane that
 * inverts with the theme changes what the anatomy looks like, which is not a theme decision). The
 * DOM chrome around the canvas — legend, buttons, the fallback line — uses the tokens and does
 * follow the theme.
 *
 * Every value below is the sRGB triple of a hex the design system already contains, named in the
 * comment, so a token change is a one-line change here rather than a hunt through shader code.
 */
import type { Rgb } from "./types";

const rgb = (hex: string): Rgb => [
  parseInt(hex.slice(1, 3), 16) / 255,
  parseInt(hex.slice(3, 5), 16) / 255,
  parseInt(hex.slice(5, 7), 16) / 255,
];

export interface ScenePalette {
  /** `--canvas` (#0b0d10). */
  background: Rgb;
  /** Skin: warm neutral, low chroma, so electrodes read against it. */
  skin: Rgb;
  /** Grey matter. */
  gm: Rgb;
  /** An unassigned marker. */
  marker: Rgb;
  /** A selected marker or region — `--accent` in the dark theme (#7fa6ff), which keeps the pane's
   *  "this is chosen" colour the same blue as the rest of the app's. */
  selected: Rgb;
  /** Hover feedback: brighter than `selected` so hovering a selected item is still visible. */
  hover: Rgb;
  /** Non-ROI regions when a region set is highlighted (plan §2.4, `target` mode). */
  dim: Rgb;
  /** Per-channel marker colours; index wraps. Channel 1 and 2 are the two TI pairs. */
  channels: [Rgb, Rgb, Rgb, Rgb];
}

export const SCENE_PALETTE: ScenePalette = {
  background: rgb("#0b0d10"),
  skin: rgb("#c8b6a6"),
  gm: rgb("#9aa6b4"),
  marker: rgb("#d8dee6"), // --line, light theme
  selected: rgb("#7fa6ff"), // --accent, dark theme
  hover: rgb("#ffffff"),
  dim: rgb("#4b5865"), // --ink-2, light theme
  channels: [rgb("#7fa6ff"), rgb("#f0a35e"), rgb("#5fc9a0"), rgb("#d98cd0")],
};

/** Default surface opacities. The skin is faint because its job is to give the electrodes a
 *  surface to sit on, not to be looked at; the grey matter is the anatomy the user is aiming at. */
export const DEFAULT_OPACITY: Record<string, number> = { skin: 0.22, gm: 0.55 };

/** Marker diameter in CSS pixels. 11 px is comfortably clickable (the WCAG 2.2 target-size floor
 *  is 24 px including spacing, and electrodes on a 10-10 net are ~20 px apart at the default
 *  framing) without covering the anatomy underneath. */
export const MARKER_SIZE_PX = 11;
