/**
 * One downloadable **part** of an example dataset, as a row — the single row component the
 * once-per-project chooser and Help ▸ Example data both draw (the maintainer's "no third copy of
 * the list"). `mode="choose"` gives the row a checkbox and the caller collects the ticked ids;
 * `mode="manage"` gives it an action column.
 *
 * The action column is deliberately quiet, because a row is a piece of chrome, not a call to
 * action:
 *
 * - **not installed** — a small secondary `Button` reading *Download*, inline, no boxed pill;
 * - **downloading or queued** — the button is *replaced* by a 4 px track spanning the column with
 *   `433 / 455 MB` beneath it in caption grey. No percentage in a grey box: the bar already is the
 *   percentage. Same `role="progressbar"` shape `TetravoxCard` uses;
 * - **installed** — a muted *Installed ✓* pill and an icon-only *Re-download* (tooltip, `force=true`)
 *   that the eye can skip;
 * - **failed** — the message as `field-error` under the row, with a *Retry* link, and the Download
 *   button stays.
 */
import { Check, RotateCw } from "lucide-react";
import { Button, IconButton } from "../../ui/Button";
import {
  formatBytes,
  isBusy,
  progressPercent,
  progressText,
  type ExamplePart,
  type ExampleStatus,
} from "./api";

export function PartRow({
  part,
  status,
  mode,
  checked = false,
  onToggle,
  onDownload,
}: {
  part: ExamplePart;
  status: ExampleStatus | undefined;
  mode: "choose" | "manage";
  /** `choose` only. */
  checked?: boolean;
  onToggle?: (partId: string) => void;
  /** `manage` only; `force` re-downloads a part that is already on disk. */
  onDownload?: (partId: string, force?: boolean) => void;
}) {
  const installed = status?.installed === true;
  const busy = isBusy(status);
  const caption = progressText(status);
  const percent = progressPercent(status);
  const failed = status?.error ?? undefined;

  const body = (
    <span className="example-part-body">
      <span className="example-part-name">{part.title}</span>
      <span className="example-part-meaning">{part.meaning}</span>
      <span className="example-part-size">{formatBytes(part.bytes)}</span>
    </span>
  );

  if (mode === "choose") {
    return (
      <li className="example-part" data-testid={`example-data-row-${part.id}`}>
        <label className="example-part-main">
          <input
            type="checkbox"
            checked={checked}
            data-testid={`example-data-check-${part.id}`}
            onChange={() => onToggle?.(part.id)}
          />
          {body}
        </label>
      </li>
    );
  }

  return (
    <li className="example-part" data-testid={`example-data-row-${part.id}`}>
      <div className="example-part-main">
        {body}
        <span className="example-part-action">
          {busy ? (
            <span className="example-part-progress" data-testid={`example-data-progress-${part.id}`}>
              <span
                className={`example-part-track${percent === undefined ? " is-indeterminate" : ""}`}
                role="progressbar"
                aria-label={`Downloading ${part.title}`}
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <span
                  className="example-part-fill"
                  style={percent === undefined ? undefined : { width: `${percent}%` }}
                />
              </span>
              <span className="example-part-bytes tabular-nums">{caption}</span>
            </span>
          ) : installed ? (
            <>
              <span
                className="example-part-installed"
                data-testid={`example-data-installed-${part.id}`}
              >
                Installed <Check size={12} aria-hidden />
              </span>
              <IconButton
                size="sm"
                variant="ghost"
                title="Re-download this part, replacing what is on disk"
                aria-label={`Re-download ${part.title}`}
                data-testid={`example-data-redownload-${part.id}`}
                icon={<RotateCw size={13} aria-hidden />}
                onClick={() => onDownload?.(part.id, true)}
              />
            </>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              data-testid={`example-data-download-${part.id}`}
              onClick={() => onDownload?.(part.id)}
            >
              Download
            </Button>
          )}
        </span>
      </div>
      {failed && (
        <div className="field-error example-part-error" data-testid={`example-data-error-${part.id}`}>
          {failed}{" "}
          <button
            type="button"
            className="example-part-retry"
            data-testid={`example-data-retry-${part.id}`}
            onClick={() => onDownload?.(part.id)}
          >
            Retry
          </button>
        </div>
      )}
    </li>
  );
}
