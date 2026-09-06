import type { JobEvent } from "./types";

export type JobLogLevel = "debug" | "info" | "warning" | "error";

export interface JobLogLine {
  seq: number;
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

/** Convert the event types that belong in a terminal to its shared line model. */
export function jobEventsToLogLines(events: readonly JobEvent[]): JobLogLine[] {
  return events
    .filter((event) => event.type === "log" || event.type === "marker")
    .map((event) => ({
      seq: event.seq,
      level: event.level as JobLogLevel | undefined,
      text: event.msg ?? "",
    }));
}
