/**
 * **E1 — the app pins a protocol RANGE and named features, never a version.**
 *
 * This file is the single place on the renderer side that says which Tetravox embed protocol
 * versions this build can host and what each level is called. Its Python twin is
 * `tit/tetravox/protocol.py`, and `tests/test_tetravox_protocol.py` reads *both files off disk*
 * and fails if they disagree — two hand-maintained copies of a compatibility table drift the
 * first time one of them is edited alone.
 *
 * The coupling this removes: until now the only thing that decided which viewer the app could
 * talk to was the bundle baked into the container image, so a Tetravox release implied a
 * TI-Toolbox release. With a range plus named features, an *additive* Tetravox release
 * (plan E5: a points layer, the point tool, a `pick` event, camera get/set — every protocol-1
 * message unchanged) is installed through Settings and used immediately, with **no change to
 * this repository at all**: its protocol number is already inside {@link SUPPORTED_EMBED_PROTOCOL},
 * and any feature it brings is either named below or declared by the embed's own manifest, which
 * the server passes through verbatim in `capabilities.tetravox_embed.features`.
 *
 * A pane therefore asks {@link embedCan}`(caps.tetravox_embed, "markers")` and never compares a
 * version number.
 */

/** Inclusive range of embed protocol versions this build can host. Keep in step with the Python twin. */
export const SUPPORTED_EMBED_PROTOCOL = { min: 1, max: 2 } as const;

/**
 * Named feature → the lowest protocol that provides it.
 *
 * 1 is the surface the Viewer already drives; 2 is the plan's E5 additions the run-page panes
 * gate on. A feature moving level is one edit here and one in `tit/tetravox/protocol.py`.
 */
export const EMBED_FEATURE_MIN_PROTOCOL = {
  volumes: 1,
  meshes: 1,
  cursor: 1,
  probe: 1,
  screenshot: 1,
  layers: 1,
  markers: 2,
  pick: 2,
  camera: 2,
} as const;

export type EmbedFeature = keyof typeof EMBED_FEATURE_MIN_PROTOCOL;

/** Where the active bundle came from (`capabilities.tetravox_embed.source`). */
export type EmbedSource = "override" | "installed" | "baked";

/**
 * `capabilities.tetravox_embed`, structurally.
 *
 * Every field past `available` is optional so this also accepts an answer from a server older
 * than E1 — in which case {@link embedCan} falls back to the protocol map below.
 */
export interface EmbedCapability {
  available: boolean;
  version?: string | null;
  protocol?: number | null;
  source?: EmbedSource | null;
  features?: string[];
  compatible?: boolean;
  supported?: { min: number; max: number } | null;
}

/** Is `protocol` an integer this build can host? A non-integer is never supported. */
export function isSupportedProtocol(protocol: unknown): boolean {
  if (typeof protocol !== "number" || !Number.isInteger(protocol)) return false;
  return protocol >= SUPPORTED_EMBED_PROTOCOL.min && protocol <= SUPPORTED_EMBED_PROTOCOL.max;
}

/** The feature names an embed at `protocol` offers, sorted. */
export function featuresForProtocol(protocol: unknown): EmbedFeature[] {
  if (typeof protocol !== "number" || !Number.isInteger(protocol)) return [];
  return (Object.keys(EMBED_FEATURE_MIN_PROTOCOL) as EmbedFeature[]).filter((name) => protocol >= EMBED_FEATURE_MIN_PROTOCOL[name]).sort();
}

/**
 * **The one question a pane asks**: can the active embed do this?
 *
 * The server's `features` list wins when it has one — it is computed from the *installed*
 * manifest and may name features this build has never heard of, which is what makes an additive
 * Tetravox release work with no change here. Without it (an older server, or a fixture), the
 * answer is derived from the protocol number and the map above.
 *
 * An unavailable embed can do nothing; so can one whose protocol is outside the supported range,
 * because this host cannot promise to drive it at all.
 */
export function embedCan(embed: EmbedCapability | null | undefined, feature: EmbedFeature | (string & {})): boolean {
  if (!embed?.available) return false;
  if (embed.features && embed.features.length > 0) return embed.features.includes(feature);
  if (!isSupportedProtocol(embed.protocol)) return false;
  return (featuresForProtocol(embed.protocol) as string[]).includes(feature);
}

/** Is the active embed one this build can drive at all? */
export function embedIsCompatible(embed: EmbedCapability | null | undefined): boolean {
  if (!embed?.available) return false;
  if (typeof embed.compatible === "boolean") return embed.compatible;
  return isSupportedProtocol(embed.protocol);
}

/** The one-line sentence a page shows when the embed cannot do what it needs. */
export function embedShortfall(embed: EmbedCapability | null | undefined, feature: EmbedFeature | (string & {})): string | null {
  if (embedCan(embed, feature)) return null;
  if (!embed?.available) return "No viewer bundle is installed. Install one in Settings → Viewer engine.";
  if (!embedIsCompatible(embed)) {
    return `The installed viewer speaks protocol ${embed.protocol ?? "?"}, outside the ${SUPPORTED_EMBED_PROTOCOL.min}–${SUPPORTED_EMBED_PROTOCOL.max} this app supports.`;
  }
  return `The installed viewer (v${embed.version ?? "?"}, protocol ${embed.protocol ?? "?"}) has no ${feature}. Update it in Settings → Viewer engine.`;
}
