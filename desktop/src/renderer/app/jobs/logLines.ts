import type { JobEvent } from "./types";

export type JobLogLevel = "debug" | "info" | "warning" | "error";

export interface JobLogLine {
  /**
   * The SOURCE EVENT's sequence number — not a line counter. Several lines can share one `seq`
   * (a single stdout chunk that carried several newline-separated lines), which is what keeps the
   * console's Clear watermark ("hide everything up to seq N") meaningful against the event stream.
   * Use {@link JobLogLine.key} when a unique identity is needed.
   */
  seq: number;
  /**
   * Unique within a transcript: `"<seq>:<index within the event>"`. Set by the producers below;
   * a caller that builds lines by hand may omit it and the console falls back to the row index.
   */
  key?: string;
  level?: JobLogLevel;
  text: string;
}

/** Merge REST history with the live socket tail, preferring the latest copy of each sequence. */
export function mergeJobEvents(...sources: readonly JobEvent[][]): JobEvent[] {
  const bySequence = new Map<number, JobEvent>();
  for (const events of sources) {
    for (const event of events) bySequence.set(event.seq, event);
  }
  return [...bySequence.values()].sort((a, b) => a.seq - b.seq);
}

/**
 * One stdout chunk → the visual lines it really is.
 *
 * The console draws each line into a virtual row of a FIXED height (18 px), so a "line" that
 * secretly contains `\n` paints several lines of text inside one row's box and over the rows below
 * it — the overlapping "Placing Electrode: / Assembling FEM Matrix" blocks the maintainer
 * screenshotted during a live simulation. SimNIBS writes exactly that: multi-line chunks, plus
 * `\r`-driven in-place progress counters.
 *
 * So: `\r\n` is one break; a bare `\r` is a carriage return, which means everything before it on
 * that line was OVERWRITTEN in a real terminal — the last segment wins, which is how a progress
 * counter collapses to its final value instead of becoming 400 rows. A chunk that ends in a
 * newline does not produce a trailing blank line; a blank line INSIDE a chunk survives, because a
 * traceback's blank separator lines are part of the log.
 */
export function splitLogText(text: string): string[] {
  const lines = text
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => {
      if (!line.includes("\r")) return line;
      const segments = line.split("\r").filter((s) => s !== "");
      return segments[segments.length - 1] ?? "";
    });
  while (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** Convert the event types that belong in a terminal to its shared line model. */
export function jobEventsToLogLines(events: readonly JobEvent[]): JobLogLine[] {
  const out: JobLogLine[] = [];
  for (const event of events) {
    if (event.type !== "log" && event.type !== "marker") continue;
    const level = event.level as JobLogLevel | undefined;
    splitLogText(event.msg ?? "").forEach((text, i) => {
      out.push({ seq: event.seq, key: `${event.seq}:${i}`, level, text });
    });
  }
  return out;
}
