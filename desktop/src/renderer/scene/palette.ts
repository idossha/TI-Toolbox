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
  /** An electrode in no channel. A neutral grey, so "in a channel" is a hue and "not" is the
   *  absence of one — colour is the whole state signal, and there is no selection ring. */
  idle: Rgb;
  /** 35 % grey — an electrode the montage cannot use. */
  disabled: Rgb;
  /** A selected marker or region — `--accent` in the dark theme (#7fa6ff), which keeps the pane's
   *  "this is chosen" colour the same blue as the rest of the app's. */
  selected: Rgb;
  /** Hover feedback: brighter than `selected` so hovering a selected item is still visible. */
  hover: Rgb;
  /** Non-ROI regions when a region set is highlighted (plan §2.4, `target` mode). */
  dim: Rgb;
  /**
   * Per-channel marker colours; index wraps.
   *
   * The **Okabe-Ito** qualitative set (Okabe & Ito 2008, "Color Universal Design") in its
   * published order minus yellow: six hues that stay separable under deuteranopia, protanopia and
   * tritanopia. The previous four had a green next to an orange, which a deuteranope reading a
   * four-pair mTI montage could not tell apart — the exact case this palette exists for. Yellow is
   * dropped because it is the one Okabe-Ito hue that does not hold up against the skin colour.
   */
  channels: [Rgb, Rgb, Rgb, Rgb, Rgb, Rgb];
}

export const SCENE_PALETTE: ScenePalette = {
  background: rgb("#0b0d10"),
  skin: rgb("#c8b6a6"),
  gm: rgb("#9aa6b4"),
  marker: rgb("#d8dee6"), // --line, light theme
  selected: rgb("#7fa6ff"), // --accent, dark theme
  hover: rgb("#ffffff"),
  dim: rgb("#4b5865"), // --ink-2, light theme
  idle: rgb("#9ea6b3"),
  disabled: rgb("#595959"),
  channels: [
    rgb("#0072B2"), // blue
    rgb("#E69F00"), // orange
    rgb("#009E73"), // bluish green
    rgb("#CC79A7"), // reddish purple
    rgb("#D55E00"), // vermillion
    rgb("#56B4E9"), // sky blue
  ],
};

/** Default surface opacities, for the surfaces that have an opacity control. The skin is faint
 *  because its job is to give the electrodes a surface to sit on, not to be looked at. The grey
 *  matter is deliberately absent: it is the anatomy the user is aiming at and is always opaque. */
export const DEFAULT_OPACITY: Record<string, number> = { skin: 0.22 };

/** Marker diameter in CSS pixels. 11 px is comfortably clickable (the WCAG 2.2 target-size floor
 *  is 24 px including spacing, and electrodes on a 10-10 net are ~20 px apart at the default
 *  framing) without covering the anatomy underneath. */
export const MARKER_SIZE_PX = 11;
