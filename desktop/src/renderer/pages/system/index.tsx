/**
 * System — real-time monitoring of the machine the jobs actually run on.
 *
 * "The machine" is whatever the **server** sees: inside the Docker deployment that is the `tit`
 * container and the resources the host has given it, which is the honest answer to "why is this
 * slow" and not the same thing as the laptop the Electron window is on. Every figure comes from
 * the one `/ws/system` snapshot the jobs rail's Host tab already reads (`ws/useSystemStream`, one
 * shared socket for the whole app), so the two surfaces cannot disagree about a number.
 *
 * **Why both this and the Host tab.** Host is the glance you take without leaving the page you
 * are on: four figures and a process list in 260 px. This is where you go when the glance said
 * something is wrong, and it is shaped like the tools people already read that way — btop for the
 * resource band, Docker Desktop for the daemon panel, htop for the processes.
 *
 * **The layout is the argument.** One screen, four questions, top to bottom: *what are the
 * resources doing* (the gauges band), *is Docker healthy* and *what is running* (the two middle
 * panels), *whose work is this* (the jobs strip). Nothing scrolls at 1440×900 in the common case,
 * because a monitor you have to scroll is a monitor you read half of.
 *
 * Nothing here is persisted. The charts are the last five minutes of the socket's own sample ring
 * and start over on a reload — a monitor, not a history; `derivatives/` is for things worth
 * keeping.
 */
import { useCallback, useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, Cpu, Gauge, HardDrive, MemoryStick } from "lucide-react";
import type { PageDef } from "../../app/registry";
import { cancelJob } from "../../app/jobs-rail/api";
import { useJobsModel } from "../../app/jobs-rail/model";
import { ApiError } from "../../api/client";
import { StatusDot } from "../../ui/Status";
import { PageLayout } from "../../ui/Layout";
import { notify } from "../../ui/Toast";
import { bytes, pct } from "../../ui/utils";
import { useSystemStream } from "../../ws/useSystemStream";
import { AreaChart } from "./AreaChart";
import { DockerPanel } from "./DockerPanel";
import { JobsStrip } from "./JobsStrip";
import { ProcessPanel } from "./ProcessPanel";
import {
  coreRows,
  diskSegments,
  formatRate,
  formatUptime,
  loadLabel,
  loadTone,
  memorySegments,
  netRate,
  seriesOf,
  swapSegments,
  toneFor,
  windowed,
  type Process,
} from "./model";
import { CoreCell, Meter, MeterLegend, Panel, Readout } from "./parts";
import "./system-page.css";

/** The three windows a load average reports, in the order psutil returns them. */
const LOAD_WINDOWS = ["1 m", "5 m", "15 m"];

function SystemPage() {
  const { status, samples } = useSystemStream();
  const jobs = useJobsModel();
  const queryClient = useQueryClient();

  const latest = samples[samples.length - 1];
  const window5m = useMemo(() => windowed(samples), [samples]);
  const cpuSeries = useMemo(() => seriesOf(window5m, (s) => s.cpu_percent), [window5m]);
  const memSeries = useMemo(() => seriesOf(window5m, (s) => s.mem.percent), [window5m]);
  const cores = useMemo(() => coreRows(samples), [samples]);
  const memSegs = useMemo(() => memorySegments(latest?.mem), [latest?.mem]);
  const swapSegs = useMemo(() => swapSegments(latest?.swap), [latest?.swap]);
  const projectSegs = useMemo(() => diskSegments(latest?.disk), [latest?.disk]);
  const dockerDiskSegs = useMemo(() => diskSegments(latest?.disk_docker), [latest?.disk_docker]);
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

  const memUsedLabel = latest ? `${bytes(latest.mem.used)} of ${bytes(latest.mem.total)}` : "—";
  const cpuLimit = latest?.docker?.own?.cpu_limit;

  return (
    <PageLayout header={<SystemHeader status={status} latest={latest} />}>
      <div className="system-page" data-testid="system-page">
        {/* ── band 1: resources ─────────────────────────────────────────── */}
        <div className="system-band" data-testid="system-band">
          <Panel
            title={
              <>
                <Cpu size={12} aria-hidden /> CPU
              </>
            }
            aside={latest ? `${latest.cpu_count} cores${cpuLimit ? ` · limit ${cpuLimit}` : ""}` : "—"}
            testId="system-cpu"
          >
            <Readout
              value={pct(latest?.cpu_percent)}
              detail={`load ${loadLabel(latest?.load_avg)}`}
              tone={toneFor(latest?.cpu_percent)}
            />
            <AreaChart timestamps={cpuSeries.timestamps} values={cpuSeries.values} label="CPU" height={88} />
            {cores.length > 0 && (
              <div className="system-cores" data-testid="system-cores">
                {cores.map((core) => (
                  <CoreCell key={core.index} core={core} />
                ))}
              </div>
            )}
          </Panel>

          <Panel
            title={
              <>
                <MemoryStick size={12} aria-hidden /> Memory
              </>
            }
            aside={memUsedLabel}
            testId="system-memory"
          >
            <Readout
              value={pct(latest?.mem.percent)}
              detail={latest ? `${bytes(latest.mem.available)} available` : "—"}
              tone={toneFor(latest?.mem.percent)}
            />
            <Meter segments={memSegs} testId="memory-meter" />
            <MeterLegend segments={memSegs} />
            <AreaChart
              timestamps={memSeries.timestamps}
              values={memSeries.values}
              label="Memory"
              height={88}
              colorVar="--success"
            />
            <div className="system-block">
              <div className="system-block-head text-caption">
                Swap
                <span className="system-block-value tabular-nums">
                  {latest?.swap
                    ? latest.swap.total === 0
                      ? "none configured"
                      : `${bytes(latest.swap.used)} of ${bytes(latest.swap.total)}`
                    : "—"}
                </span>
              </div>
              <Meter segments={swapSegs} testId="swap-meter" />
            </div>
          </Panel>

          <Panel
            title={
              <>
                <HardDrive size={12} aria-hidden /> Storage
              </>
            }
            aside={latest?.disk ? `${bytes(latest.disk.free)} free` : "—"}
            testId="system-storage"
          >
            <div className="system-block">
              <div className="system-block-head text-caption">
                Project volume
                <span className="system-block-value mono">{latest?.disk?.path || "—"}</span>
              </div>
              <Meter segments={projectSegs} testId="project-disk-meter" />
              <p className="system-note text-caption tabular-nums">
                {latest?.disk ? `${bytes(latest.disk.free)} free of ${bytes(latest.disk.total)}` : "—"}
              </p>
            </div>
            <div className="system-block">
              <div className="system-block-head text-caption">
                Docker root
                <span className="system-block-value mono">{latest?.disk_docker?.path || "not visible"}</span>
              </div>
              {latest?.disk_docker ? (
                <>
                  <Meter segments={dockerDiskSegs} testId="docker-disk-meter" />
                  <p className="system-note text-caption tabular-nums">
                    {bytes(latest.disk_docker.free)} free of {bytes(latest.disk_docker.total)}
                  </p>
                </>
              ) : (
                /* The normal case from inside the container: the socket is bind-mounted, the
                   graph directory is not. `docker system df` in the Docker panel answers the
                   question this reading was standing in for. */
                <p className="system-note text-caption">
                  The daemon&apos;s storage is outside this container — see Docker for what it holds.
                </p>
              )}
            </div>
            {/* Bind mounts are a *storage* fact — what of the host is visible in here, and
                whether it is writable — so they live beside the two filesystems rather than in
                the Docker panel, where they were one more line in a column of daemon facts. */}
            {(latest?.docker?.own?.mounts ?? []).length > 0 && (
              <div className="system-block">
                <div className="system-block-head text-caption">Mounts</div>
                <table className="system-mini" data-testid="system-mounts">
                  <tbody>
                    {latest!.docker!.own!.mounts!.map((m) => (
                      <tr key={m.destination}>
                        <td className="mono system-mini-strong">{m.destination}</td>
                        <td className="mono system-mini-dim system-mini-ellipsis">{m.source}</td>
                        <td className="system-mini-num system-mini-dim">{m.mode || "rw"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel
            title={
              <>
                <Gauge size={12} aria-hidden /> Host
              </>
            }
            aside={formatUptime(latest?.uptime_s)}
            testId="system-host"
          >
            {/* The load average, drawn against the core count: "1.42" means nothing until you
                know whether this machine has 2 cores or 32, and the bar is that comparison. */}
            {(latest?.load_avg ?? []).length > 0 && (
              <div className="system-block" data-testid="system-load">
                {latest!.load_avg!.map((value, i) => {
                  const cores = latest!.cpu_count || 1;
                  return (
                    <div
                      key={LOAD_WINDOWS[i] ?? i}
                      className="system-load"
                      data-tone={loadTone([value], cores)}
                      title={`${value.toFixed(2)} over ${LOAD_WINDOWS[i] ?? "?"}, on ${cores} cores`}
                    >
                      <span className="system-load-label text-caption">{LOAD_WINDOWS[i] ?? ""}</span>
                      <div className="system-load-track">
                        <div
                          className="system-load-fill"
                          style={{ width: `${Math.max(1, Math.min(100, (value / cores) * 100))}%` }}
                        />
                      </div>
                      <span className="system-load-value text-caption tabular-nums">{value.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
            )}
            <dl className="system-kv" data-testid="system-host-kv">
              <dt>Network</dt>
              <dd className="tabular-nums">
                {rate ? `↓ ${formatRate(rate.recv)} · ↑ ${formatRate(rate.sent)}` : "—"}
              </dd>
              <dt>Processes</dt>
              <dd className="tabular-nums">{latest?.process_total ?? "—"}</dd>
              <dt>Kernels</dt>
              <dd className="tabular-nums">{latest?.kernels ?? 0}</dd>
              <dt>Server</dt>
              <dd className="tabular-nums">
                {latest?.own ? `pid ${latest.own.pid} · ${bytes(latest.own.rss)}` : "—"}
              </dd>
            </dl>
          </Panel>
        </div>

        {/* ── band 2: Docker | processes ────────────────────────────────── */}
        <div className="system-middle">
          <DockerPanel docker={latest?.docker} />
          <ProcessPanel snapshot={latest} onStop={onStopProcess} />
        </div>

        {/* ── band 3: the work ──────────────────────────────────────────── */}
        <JobsStrip model={jobs} />
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
