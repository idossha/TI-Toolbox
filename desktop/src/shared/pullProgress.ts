/**
 * One progress line on its way to the launcher, from either of the two sources the stack has.
 *
 * `formatPullEvent` is the live one: image pulls now arrive as the Engine API's structured NDJSON
 * objects (`main/docker/engine.ts#pullImage`), and it renders each into the same
 * `ParsedProgressLine` the launcher UI already knows how to display, so replacing the CLI did not
 * change one line of that UI. `parseProgressLine` is still what container log lines go through —
 * they arrive as raw text with ANSI escapes and carriage returns like the CLI's output did.
 *
 * Ported from the layer-tracking regex in `package/src/renderer.js:133-249` (`appendActivity`),
 * pulled out as a pure function so both the main process (which decides what to forward) and the
 * launcher UI (which decides how to render it, e.g. updating a layer's line in place instead of
 * appending) share one definition of "what is a docker pull-progress line".
 */

export interface ParsedProgressLine {
  /** ANSI-stripped, CR-collapsed line text. */
  message: string;
  /** Docker layer id, when `message` is a `<layer> Pulling|Downloading|...` line. */
  layerId?: string;
  status?: string;
  /** True for a terminal per-layer status ("Pull complete" etc.) — stop tracking this layer. */
  isComplete?: boolean;
  /** True for a Braille spinner frame (`simnibs`/compose's own "please wait" animation). */
  isSpinner: boolean;
}

const LAYER_RE = /^\s*(\w+)\s+(Pulling|Downloading|Extracting|Waiting|Verifying Checksum|Download complete|Pull complete|Already exists)/;
const SPINNER_RE = /^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]/;
const COMPLETE_STATUSES = new Set(["Download complete", "Pull complete", "Already exists"]);

/** The fields of Docker's pull-progress NDJSON object this renderer reads. */
export interface PullEvent {
  id?: string;
  status?: string;
  progressDetail?: { current?: number; total?: number };
  progress?: string;
}

/**
 * One Engine API pull-progress object rendered into the same shape (and the same wording) the CLI
 * used to print: `"<layer> Downloading 42%"`. The percentage comes from `progressDetail`, not from
 * Docker's own `progress` string, which is a fixed-width ASCII progress bar meant for a terminal.
 */
export function formatPullEvent(event: PullEvent): ParsedProgressLine {
  const status = (event.status ?? "").trim();
  const current = event.progressDetail?.current;
  const total = event.progressDetail?.total;
  const percent = typeof current === "number" && typeof total === "number" && total > 0 ? ` ${Math.min(100, Math.round((current / total) * 100))}%` : "";
  const message = event.id ? `${event.id} ${status}${percent}` : status;
  const parsed: ParsedProgressLine = { message, isSpinner: false };
  if (event.id) {
    parsed.layerId = event.id;
    parsed.status = status;
    parsed.isComplete = COMPLETE_STATUSES.has(status);
  }
  return parsed;
}

export function parseProgressLine(raw: string): ParsedProgressLine {
  // eslint-disable-next-line no-control-regex -- stripping real ANSI escape sequences.
  const message = raw.replace(/\x1b\[[0-9;]*[A-Za-z]/g, "").replace(/\r/g, "").trim();
  const layerMatch = message.match(LAYER_RE);
  const isSpinner = SPINNER_RE.test(message);
  if (!layerMatch) return { message, isSpinner };
  const layerId = layerMatch[1] ?? "";
  const status = layerMatch[2] ?? "";
  return { message, layerId, status, isComplete: COMPLETE_STATUSES.has(status), isSpinner };
}
