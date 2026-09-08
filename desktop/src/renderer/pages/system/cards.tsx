/**
 * The right-hand stack: Memory, Storage, Host. Compact, one question each, and — the constraint
 * that shapes all three — **no number that appears anywhere else on the page** (`METRIC_HOME`).
 *
 * That is why Memory has no percentage headline and Storage has no second chart: the percentages
 * live in the timeline's legend, which is the live read-out. What is left in these cards is the
 * part a percentage cannot say — the *composition* of the memory, and what is actually occupying
 * the disk.
 */
import type { SystemSnapshot } from "../../api/client";
import { bytes } from "../../ui/utils";
import {
  diskSegments,
  dockerSegments,
  dockerTotal,
  formatRate,
  formatUptime,
  memorySegments,
  metricsOf,
  swapSegments,
  loadTone,
  type Rate,
} from "./model";
import { Meter, MeterLegend, Panel } from "./parts";

export function MemoryCard({ latest }: { latest: SystemSnapshot | undefined }) {
  const mem = memorySegments(latest?.mem);
  const swap = swapSegments(latest?.swap);
  return (
    <Panel
      title="Memory"
      aside={latest ? `${bytes(latest.mem.available)} available` : "—"}
      testId="system-memory"
      metrics={metricsOf("memory")}
    >
      {/* The composition, not the percentage: a container at "92 % memory" where a third of it is
          page cache is not in trouble, and one undifferentiated block cannot say so. */}
      <Meter segments={mem} testId="memory-meter" />
      <MeterLegend segments={mem} />
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
        <Meter segments={swap} testId="swap-meter" />
      </div>
    </Panel>
  );
}

/**
 * Storage answers one question — *what is filling this machine's disk* — and it takes both halves
 * of the answer, because from inside the container they are different sources for the same
 * question. The project volume is a filesystem reading; `docker system df` is the daemon's own
 * accounting, and it is the only answer available at all when `/var/lib/docker` is not visible
 * from in here (the normal case: the socket is bind-mounted, the graph directory is not).
 */
export function StorageCard({ latest }: { latest: SystemSnapshot | undefined }) {
  const project = diskSegments(latest?.disk);
  const dockerRoot = diskSegments(latest?.disk_docker);
  const df = latest?.docker?.df ?? null;
  const dfSegments = dockerSegments(df);
  const reclaimable = df?.images_reclaimable ?? 0;

  // No `aside`: "412 GB free" in the header and "412 GB free of 1000 GB" under the meter is the
  // same number twice, three lines apart.
  return (
    <Panel
      title="Storage"
      testId="system-storage"
      metrics={metricsOf("storage")}
    >
      <div className="system-block">
        <div className="system-block-head text-caption">
          Project volume
          <span className="system-block-value mono">{latest?.disk?.path || "—"}</span>
        </div>
        <Meter segments={project} testId="project-disk-meter" />
        <p className="system-note text-caption tabular-nums">
          {latest?.disk ? `${bytes(latest.disk.free)} free of ${bytes(latest.disk.total)}` : "—"}
        </p>
      </div>

      {latest?.disk_docker && (
        <div className="system-block">
          <div className="system-block-head text-caption">
            Docker root
            <span className="system-block-value mono">{latest.disk_docker.path}</span>
          </div>
          <Meter segments={dockerRoot} testId="docker-disk-meter" />
        </div>
      )}

      <div className="system-block">
        <div className="system-block-head text-caption">
          Used by Docker
          <span className="system-block-value tabular-nums">{df ? bytes(dockerTotal(df)) : "—"}</span>
        </div>
        <Meter segments={dfSegments} testId="docker-df-meter" />
        <MeterLegend segments={dfSegments} />
        {reclaimable > 0 && (
          <p className="system-note system-note-warn text-caption tabular-nums" data-testid="docker-reclaimable">
            {bytes(reclaimable)} reclaimable — `docker image prune`
          </p>
        )}
      </div>
    </Panel>
  );
}

/** The three windows a load average reports, in the order psutil returns them. */
const LOAD_WINDOWS = ["1 m", "5 m", "15 m"];

export function HostCard({ latest, rate }: { latest: SystemSnapshot | undefined; rate: Rate | null }) {
  const load = latest?.load_avg ?? [];
  const cores = latest?.cpu_count || 1;
  return (
    <Panel title="Host" aside={formatUptime(latest?.uptime_s)} testId="system-host" metrics={metricsOf("host")}>
      {/* Three numbers, not three bars: the bars were a second drawing of a figure the timeline
          above already draws the shape of, and the ratio to the core count is what makes a load
          average readable — so that is what the tone carries. */}
      {load.length > 0 && (
        <div className="system-loads" data-testid="system-load">
          {load.map((value, i) => (
            <span key={LOAD_WINDOWS[i] ?? i} className="system-load-cell" data-tone={loadTone([value], cores)}>
              <span className="text-caption system-load-window">{LOAD_WINDOWS[i] ?? ""}</span>
              <span className="system-load-num tabular-nums">{value.toFixed(2)}</span>
            </span>
          ))}
          <span className="system-load-cell system-load-cores">
            <span className="text-caption system-load-window">cores</span>
            <span className="system-load-num tabular-nums">{cores}</span>
          </span>
        </div>
      )}
      <dl className="system-kv">
        <dt>Network</dt>
        <dd className="tabular-nums">{rate ? `↓ ${formatRate(rate.recv)} · ↑ ${formatRate(rate.sent)}` : "—"}</dd>
        <dt>Processes</dt>
        <dd className="tabular-nums">{latest?.process_total ?? "—"}</dd>
        <dt>Kernels</dt>
        <dd className="tabular-nums">{latest?.kernels ?? 0}</dd>
        <dt>Server</dt>
        {/* Uptime is the card's `aside` and appears nowhere else. */}
        <dd className="tabular-nums">{latest?.own ? `pid ${latest.own.pid} · ${bytes(latest.own.rss)}` : "—"}</dd>
      </dl>
    </Panel>
  );
}
