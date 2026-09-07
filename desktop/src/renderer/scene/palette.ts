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

/**
 * A qualitative ramp for **per-item identity**, indexed by position and wrapping only past 12.
 *
 * `channels` above answers "which stimulation pair", and six hues is the honest size of that
 * question. This answers "which electrode", which a free-hand placement asks once per row: the dot
 * on the scalp and the swatch in the table have to name the same one, and a six-hue ramp reused for
 * an eight-position mTI montage would put the same colour on two different electrodes.
 *
 * Seven Okabe-Ito hues (Okabe & Ito 2008, including the yellow this file's `channels` drops — a
 * name label sits next to every dot here, so a hue that is weak against the skin is still
 * identified; its eighth, black, is invisible on a `#0b0d10` canvas and is left out) followed by
 * five from Paul Tol's bright and muted qualitative sets, chosen to stay separable from the seven
 * before them under deuteranopia and protanopia.
 */
export const SCENE_CATEGORICAL: readonly Rgb[] = [
  rgb("#0072B2"), // blue
  rgb("#E69F00"), // orange
  rgb("#009E73"), // bluish green
  rgb("#CC79A7"), // reddish purple
  rgb("#D55E00"), // vermillion
  rgb("#56B4E9"), // sky blue
  rgb("#F0E442"), // yellow
  rgb("#EE6677"), // Tol bright red — Okabe-Ito's eighth is black, which is invisible on this canvas
  rgb("#882255"), // Tol wine
  rgb("#44AA99"), // Tol teal
  rgb("#999933"), // Tol olive
  rgb("#AA4499"), // Tol purple
];

/** `[r, g, b]` in 0..1 back to the `#rrggbb` a DOM swatch needs — the same numbers the shader gets,
 *  so a swatch can never drift from its dot. */
export function rgbToHex(color: Rgb): string {
  const byte = (v: number) => Math.round(Math.min(1, Math.max(0, v)) * 255);
  return `#${[byte(color[0]), byte(color[1]), byte(color[2])].map((n) => n.toString(16).padStart(2, "0")).join("")}`;
}

/** The ramp's *n*-th colour, wrapping. */
export function categoricalColor(index: number): Rgb {
  return SCENE_CATEGORICAL[((index % SCENE_CATEGORICAL.length) + SCENE_CATEGORICAL.length) % SCENE_CATEGORICAL.length] as Rgb;
}

/** Default surface opacities, for the surfaces that have an opacity control. The skin is faint
 *  because its job is to give the electrodes a surface to sit on, not to be looked at. The grey
 *  matter is deliberately absent: it is the anatomy the user is aiming at and is always opaque. */
export const DEFAULT_OPACITY: Record<string, number> = { skin: 0.22 };

/** Marker diameter in CSS pixels. 11 px is comfortably clickable (the WCAG 2.2 target-size floor
 *  is 24 px including spacing, and electrodes on a 10-10 net are ~20 px apart at the default
 *  framing) without covering the anatomy underneath. */
export const MARKER_SIZE_PX = 11;
