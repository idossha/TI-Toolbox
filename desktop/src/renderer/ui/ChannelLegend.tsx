/**
 * The channel legend above the montage scene pane (plan `v3-tetravox-selection-pipeline-plan.md`
 * §1-B, B4).
 *
 * One chip per montage pair: the pair's colour, and the pair itself as `"E1 → E2"`. It answers the
 * two questions the coloured dots raise and cannot answer themselves — *which hue is pair 2* and
 * *which pair does the next click fill* — and clicking a chip makes that pair the active one, so
 * the user can go back and fix pair 1 of a four-pair mTI montage without reaching for the form.
 *
 * It is deliberately not a selection control of its own: the pairs are the form's, and the only
 * state this owns is which of them the pane's cursor sits in.
 */
import { channelCss } from "../pages/_shared/scene/model";

export interface ChannelLegendProps {
  /** The form's pairs, in order. An empty slot renders as a placeholder, not as a gap. */
  pairs: readonly (readonly [string, string])[];
  /** The pair the next scene click fills. */
  activeChannel: number | null;
  onActivate?: (channel: number) => void;
  className?: string;
}

/** `"E1 → E2"`, with an em-dash placeholder for a slot nobody has filled yet. */
export function channelLabel(pair: readonly [string, string]): string {
  const a = pair[0] || "—";
  const b = pair[1] || "—";
  return `${a} → ${b}`;
}

export function ChannelLegend({ pairs, activeChannel, onActivate, className }: ChannelLegendProps) {
  if (pairs.length === 0) return null;
  return (
    <div
      className={`channel-legend ${className ?? ""}`.trim()}
      role="group"
      aria-label="Montage channels"
      data-testid="channel-legend"
    >
      {pairs.map((pair, channel) => {
        const active = channel === activeChannel;
        return (
          <button
            key={channel}
            type="button"
            className="channel-chip"
            data-testid={`channel-chip-${channel}`}
            data-channel={channel}
            data-active={active ? "true" : "false"}
            data-color={channelCss(channel)}
            aria-pressed={active}
            title={`Pair ${channel + 1}: ${channelLabel(pair)}`}
            onClick={() => onActivate?.(channel)}
          >
            <span className="channel-chip-dot" style={{ background: channelCss(channel) }} aria-hidden />
            <span className="channel-chip-name">{channelLabel(pair)}</span>
          </button>
        );
      })}
    </div>
  );
}
