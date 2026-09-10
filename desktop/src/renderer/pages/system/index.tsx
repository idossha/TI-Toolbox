/**
 * System — real-time monitoring of the machine the jobs actually run on.
 *
 * "The machine" is whatever the **server** sees: inside the Docker deployment that is the `tit`
 * container and the resources the host has given it, which is the honest answer to "why is this
 * slow" and not the same thing as the laptop the Electron window is on. Every figure comes from
 * the one `/ws/system` snapshot the jobs rail's Host tab already reads (`ws/useSystemStream`, one
 * shared socket for the whole app), so the two surfaces cannot disagree about a number.
 *
 * **The layout is the argument** (maintainer, 2026-09-07). Two columns, full height.
 *
 * The left column is the live picture and its explanation, at one width: a rolling five-minute
 * timeline with CPU and memory on a shared x-axis — the question people have is whether the two
 * moved *together* — and directly beneath it the process table that answers *why*. Reading down
 * one column is "the machine is at 90 %" → "…because of this", which is why the two share a width
 * rather than the chart spanning the page above a narrower table.
 *
 * The right column is the standing facts: memory composition, storage, Docker, host. They change
 * slowly, they are read on purpose rather than watched, and they take the remaining width.
 *
 * There is no jobs strip. The rail is on every screen and `pages/jobs` is the full list; a third
 * view of the same rows was this page's own largest redundancy, and it took its height from the
 * process table.
 *
 * **Nothing is shown twice.** `model.ts`'s `METRIC_HOME` assigns each metric exactly one card,
 * every card publishes its own list as `data-metrics`, and `tests/unit/system-redundancy.test.tsx`
 * checks the rule against the rendered DOM. A number in two places is a number a reader has to
 * check for agreement.
 *
 * Nothing here is persisted. The timeline is the socket's own five-minute sample ring and starts
 * over on a reload — a monitor, not a history; `derivatives/` is for things worth keeping.
 */
import { useCallback, useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import type { PageDef } from "../../app/registry";
import { cancelJob } from "../../app/jobs-rail/api";
import { ApiError } from "../../api/client";
import { StatusDot } from "../../ui/Status";
import { PageLayout } from "../../ui/Layout";
import { notify } from "../../ui/Toast";
import { useSystemStream } from "../../ws/useSystemStream";
import { HostCard, MemoryCard, StorageCard } from "./cards";
import { DockerPanel } from "./DockerPanel";
import { ProcessPanel } from "./ProcessPanel";
import { Timeline } from "./Timeline";
import { netRate, windowed, type Process } from "./model";
import "./system-page.css";

function SystemPage() {
  const { status, samples } = useSystemStream();
  const queryClient = useQueryClient();

  const latest = samples[samples.length - 1];
  const window5m = useMemo(() => windowed(samples), [samples]);
  const rate = useMemo(() => netRate(samples), [samples]);

  const stop = useMutation({
    mutationFn: (jobId: string) => cancelJob(jobId),
    onSuccess: () => {
      notify.success("Stop requested.");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => notify.error("Could not stop it.", e instanceof ApiError ? e.message : String(e)),
  });

  /**
   * Stopping from the process table goes through the *job's* cancel, never a raw kill of the pid
   * the row happens to name: a SimNIBS run is a tree, and killing one of its children leaves the
   * job's lock held and its parent waiting on a process that will never report.
   */
  const onStopProcess = useCallback(
    (p: Process) => {
      if (p.owner_kind === "job" && p.owner_id) {
        stop.mutate(p.owner_id);
        return;
      }
      // A kernel has its own lifecycle route (`DELETE /api/kernels/{id}`), owned by the notebooks
      // lane; until this page is wired to it, say so rather than doing something adjacent.
      notify.error("Kernels are stopped from Notebooks.", "This page reports them; it does not own their lifecycle.");
    },
    [stop],
  );

  return (
    <PageLayout header={<SystemHeader status={status} latest={latest} />}>
      <div className="system-page" data-testid="system-page">
        {/* Left: the timeline and the processes it explains, at the SAME width — they are one
            column, read top to bottom ("the machine is at 90 %" → "…because of this"). Right: the
            standing facts, stacked, taking the rest of the width for the full height. */}
        <div className="system-main">
          <Timeline samples={window5m} latest={latest} />
          <ProcessPanel snapshot={latest} onStop={onStopProcess} />
        </div>
        <div className="system-stack">
          <MemoryCard latest={latest} />
          <StorageCard latest={latest} />
          <DockerPanel docker={latest?.docker} />
          <HostCard latest={latest} rate={rate} />
        </div>
      </div>
    </PageLayout>
  );
}

/** System, Settings and Help are the three pages DESIGN.md §2.3 allows a header, capped at one
 *  28px eyebrow. This one also carries the live/disconnected dot — the thing a monitor must say
 *  about itself before anything it shows can be believed. */
function SystemHeader({ status, latest }: { status: string; latest: { ts: number } | undefined }) {
  return (
    <div className="page-header system-header" style={{ height: "var(--row-h)", alignItems: "center" }}>
      <h1 className="text-eyebrow" style={{ margin: 0 }}>
        System
      </h1>
      <span className="system-ws-status" data-testid="system-ws-status">
        <StatusDot
          kind={status === "open" ? "success" : status === "reconnecting" ? "warning" : "neutral"}
          pulse={status === "reconnecting"}
          title={
            status === "open"
              ? "Live updates connected"
              : status === "reconnecting"
                ? "Reconnecting to live updates…"
                : "Live updates disconnected"
          }
        />
        <span className="text-caption">
          {status === "open" ? "Live" : status === "reconnecting" ? "Reconnecting…" : "Disconnected"}
        </span>
        {latest && (
          <span className="text-caption system-ws-stamp tabular-nums">
            {new Date(latest.ts * 1000).toLocaleTimeString()}
          </span>
        )}
      </span>
    </div>
  );
}

const page: PageDef = {
  id: "system",
  title: "System",
  purpose: "Live CPU, memory, storage, Docker health and running processes on the machine the server runs on.",
  navGroup: "system",
  order: 89,
  icon: Activity,
  Component: SystemPage,
  enabled: true,
};

export default page;
