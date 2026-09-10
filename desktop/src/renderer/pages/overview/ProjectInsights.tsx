import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { components } from "../../api/schema";
import "./project-insights.css";

export type ProjectSummary = components["schemas"]["ProjectSummary"];

export async function getProjectSummary(
  signal?: AbortSignal,
): Promise<ProjectSummary> {
  const response = await fetch("/api/catalog/project-summary", {
    credentials: "same-origin",
    signal,
  });
  if (!response.ok) throw new Error("Project summary unavailable");
  return response.json() as Promise<ProjectSummary>;
}

export function formatStorage(bytes: number): string {
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const index =
    bytes > 0
      ? Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
      : 0;
  return `${(bytes / 1024 ** index).toLocaleString(undefined, { maximumFractionDigits: index ? 1 : 0 })} ${units[index]}`;
}

export function activityCalendar(
  days: ProjectSummary["activity"]["days"],
  today = new Date(),
) {
  const end = Date.UTC(
    today.getUTCFullYear(),
    today.getUTCMonth(),
    today.getUTCDate(),
  );
  const counts = new Map(days.map((day) => [day.date, day.count]));
  return Array.from({ length: 365 }, (_, i) => {
    const date = new Date(end - (364 - i) * 86400000)
      .toISOString()
      .slice(0, 10);
    return { date, count: counts.get(date) ?? 0 };
  });
}

function timestamp(value: string) {
  return new Date(value).toLocaleString(undefined, {
    timeZone: "UTC",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function ProjectInsights() {
  const query = useQuery({
    queryKey: ["project-summary"],
    queryFn: ({ signal }) => getProjectSummary(signal),
    staleTime: 30000,
    refetchInterval: (q) =>
      q.state.data?.storage.state === "scanning" ? 2000 : 60000,
  });
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  if (!query.data)
    return (
      <p className="project-insights-status" role="status">
        {query.isError
          ? "Project summary unavailable."
          : "Loading project summary…"}
      </p>
    );
  const { identity, storage, activity } = query.data;
  const days = activityCalendar(activity.days);
  const offset = new Date(`${days[0]!.date}T00:00:00Z`).getUTCDay();
  const months = days.flatMap((day, i) =>
    i === 0 || day.date.endsWith("-01")
      ? [
          {
            label: new Date(`${day.date}T00:00:00Z`).toLocaleString(undefined, {
              month: "short",
              timeZone: "UTC",
            }),
            column: Math.floor((i + offset) / 7) + 1,
          },
        ]
      : [],
  );
  const peak = Math.max(1, ...days.map((day) => day.count));
  const total = days.reduce((sum, day) => sum + day.count, 0);
  const selected = days.find((day) => day.date === selectedDay);
  const rows = [
    ...storage.derivatives,
    ...(storage.other_bytes !== null
      ? [{ name: "Other project data", bytes: storage.other_bytes }]
      : []),
  ];
  return (
    <section className="project-insights" aria-label="Project information">
      <header className="project-insights-header">
        <div>
          <h2>{identity.name}</h2>
          <p className="project-insights-path" title={identity.path}>
            {identity.path}
          </p>
        </div>
        <div className="project-insights-total">
          <strong>
            {storage.total_bytes === null
              ? "—"
              : formatStorage(storage.total_bytes)}
          </strong>
          <span>Project data</span>
        </div>
      </header>
      <div className="project-insights-grid">
        <section aria-label="Project storage">
          <h3>Storage</h3>
          <div className="project-storage-list">
            {rows.map((row) => (
              <div className="project-storage-row" key={row.name}>
                <span title={row.name}>{row.name}</span>
                <span>{formatStorage(row.bytes)}</span>
                <div className="project-storage-track" aria-hidden="true">
                  <span
                    style={{
                      width: `${storage.total_bytes ? Math.min(100, (100 * row.bytes) / storage.total_bytes) : 0}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="project-insights-caption" role="status">
            {storage.state === "scanning"
              ? "Measuring project data…"
              : storage.state === "error"
                ? "Storage scan unavailable."
                : storage.scanned_at
                  ? `Measured ${timestamp(storage.scanned_at)} UTC`
                  : "No storage measurement yet."}
          </p>
          <p className="project-insights-caption">
            File sizes; symlinks excluded.
          </p>
          {identity.created_at && (
            <p className="project-insights-caption">
              Created {timestamp(identity.created_at)} UTC
            </p>
          )}
        </section>
        <section className="project-activity" aria-label="Project activity">
          <div className="project-activity-heading">
            <h3>Activity</h3>
            <span>
              {total} recorded {total === 1 ? "job" : "jobs"} in the past year
            </span>
          </div>
          <div className="project-calendar-scroll">
            <div className="project-calendar-months" aria-hidden="true">
              {months.map((month, i) => (
                <span key={i} style={{ gridColumn: month.column }}>
                  {month.label}
                </span>
              ))}
            </div>
            <div className="project-calendar" aria-label="Daily recorded jobs">
              {Array.from({ length: offset }, (_, i) => (
                <span key={`pad-${i}`} />
              ))}
              {days.map((day) => (
                <button
                  key={day.date}
                  type="button"
                  className="project-calendar-day"
                  data-level={
                    day.count
                      ? Math.max(1, Math.ceil((4 * day.count) / peak))
                      : 0
                  }
                  title={`${day.date}: ${day.count} recorded jobs`}
                  aria-label={`${day.date}: ${day.count} recorded jobs`}
                  aria-pressed={day.date === selectedDay}
                  onClick={() => setSelectedDay(day.date)}
                />
              ))}
            </div>
          </div>
          <p className="project-insights-caption" aria-live="polite">
            {selected
              ? `${selected.date}: ${selected.count} recorded jobs. `
              : ""}
            Recorded jobs · UTC · Retained history only
            {activity.history_since
              ? ` · Since ${activity.history_since.slice(0, 10)}`
              : ""}
          </p>

        </section>
      </div>
    </section>
  );
}
