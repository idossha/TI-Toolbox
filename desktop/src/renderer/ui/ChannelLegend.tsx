/**
 * The channel legend above the montage scene pane (plan `v3-tetravox-selection-pipeline-plan.md`
 * §1-B, B4).
 *
 * One chip per montage channel: the channel's colour, and its two electrodes by role as
 * `"E1+ F3 · E1- F4"` (channel k is Ek+ and Ek-, `electrodeSlotName`). It answers the two questions
 * the coloured dots raise and cannot answer themselves — *which hue is channel 2* and *which
 * channel does the next click fill* — and clicking a chip makes that channel the active one, so
 * the user can go back and fix channel 1 of a four-channel mTI montage without reaching for the form.
 *
 * It is deliberately not a selection control of its own: the pairs are the form's, and the only
 * state this owns is which of them the pane's cursor sits in.
 */
import { channelCss, channelElectrodes, channelName } from "../pages/_shared/scene/model";

export interface ChannelLegendProps {
  /** The form's channels (electrode pairs), in order. An empty slot renders as a placeholder. */
  pairs: readonly (readonly [string, string])[];
  /** The channel the next scene click fills. */
  activeChannel: number | null;
  onActivate?: (channel: number) => void;
  className?: string;
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
            title={`${channelName(channel)}: ${channelElectrodes(pair, channel)}`}
            onClick={() => onActivate?.(channel)}
          >
            <span className="channel-chip-dot" style={{ background: channelCss(channel) }} aria-hidden />
            <span className="channel-chip-name">{channelElectrodes(pair, channel)}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * The bucket legend above the Optimizer's scene pane — the same chip row, for a search's electrode
 * buckets instead of a montage's pairs.
 *
 * It answers the two questions the coloured dots raise and cannot answer themselves — *which hue
 * is E2-* and *which bucket does the next click fill* — and clicking a chip makes that bucket the
 * active one. Like `ChannelLegend` it owns no selection: the buckets are the row's form state, and
 * the only thing this holds is which of them the next pick goes into.
 */
export interface BucketLegendProps {
  buckets: readonly { key: string; label: string; channel: number; count: number }[];
  activeKey: string | null;
  onActivate?: (key: string) => void;
  className?: string;
}

export function BucketLegend({ buckets, activeKey, onActivate, className }: BucketLegendProps) {
  if (buckets.length === 0) return null;
  return (
    <div
      className={`channel-legend ${className ?? ""}`.trim()}
      role="group"
      aria-label="Electrode buckets"
      data-testid="bucket-legend"
    >
      {buckets.map((bucket) => {
        const active = bucket.key === activeKey;
        return (
          <button
            key={bucket.key}
            type="button"
            className="channel-chip"
            data-testid={`bucket-chip-${bucket.key}`}
            data-bucket={bucket.key}
            data-channel={bucket.channel}
            data-count={bucket.count}
            data-active={active ? "true" : "false"}
            data-color={channelCss(bucket.channel)}
            aria-pressed={active}
            title={`${bucket.label}: ${bucket.count} electrode${bucket.count === 1 ? "" : "s"}`}
            onClick={() => onActivate?.(bucket.key)}
          >
            <span className="channel-chip-dot" style={{ background: channelCss(bucket.channel) }} aria-hidden />
            <span className="channel-chip-name">{`${bucket.label} · ${bucket.count}`}</span>
          </button>
        );
      })}
    </div>
  );
}
