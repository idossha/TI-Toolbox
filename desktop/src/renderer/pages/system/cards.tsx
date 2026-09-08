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
import { ChevronRight } from "lucide-react";
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
 * Storage, in two clearly separated halves (maintainer, 2026-09-07):
 *
 * **System disk** — the machine's limit. The volume the project sits on, and what Docker is
 * holding on it, because on a single-disk deployment those compete for the same free space and
 * `docker system df` is the only view of the daemon's half from inside the container.
 *
 * **This project** — our share of that limit, broken down the way a person thinks about their
 * project ("the flex searches are 180 GB"), not by directory. It comes from a *different kind of
 * read*: a full walk of the project (`GET /api/system/storage`), cached on disk and refreshed in
 * the background, so the card carries its own age and a Rescan button rather than pretending to
 * be as live as everything else on the page.
 */
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { IconButton } from "../../ui/Button";
import { getStorage, useStorage } from "./storageApi";
import { projectSegments, projectShareOfDisk, scanAgeLabel } from "./model";

export function StorageCard({ latest }: { latest: SystemSnapshot | undefined }) {
  const system = diskSegments(latest?.disk);
  const dockerRoot = diskSegments(latest?.disk_docker);
  const df = latest?.docker?.df ?? null;
  const dfSegments = dockerSegments(df);
  const reclaimable = df?.images_reclaimable ?? 0;

  const storage = useStorage();
  const project = storage.data;
  const projectBands = projectSegments(project);
  const share = projectShareOfDisk(project, latest?.disk);
  const [showKinds, setShowKinds] = useState(false);

  // A one-second tick would be silly for a figure that changes every ten minutes; a minute is
  // enough for "scanned 3 min ago" to stay honest.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);

  const queryClient = useQueryClient();
  const rescan = useMutation({
    mutationFn: () => getStorage(true),
    onSuccess: (data) => queryClient.setQueryData(["system-storage"], data),
  });

  return (
    <Panel title="Storage" testId="system-storage" metrics={metricsOf("storage")}>
      {/* ── the machine's limit ── */}
      <div className="system-block" data-testid="storage-system">
        <div className="system-block-head text-caption">
          System disk
          <span className="system-block-value mono">{latest?.disk?.path || "—"}</span>
        </div>
        <Meter segments={system} testId="project-disk-meter" />
        <p className="system-note text-caption tabular-nums">
          {latest?.disk ? `${bytes(latest.disk.free)} free of ${bytes(latest.disk.total)}` : "—"}
        </p>

        {latest?.disk_docker && <Meter segments={dockerRoot} testId="docker-disk-meter" />}

        <div className="system-subblock">
          <div className="system-block-head text-caption">
            Docker on it
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
      </div>

      {/* ── our share of it ── */}
      <div className="system-block" data-testid="storage-project">
        <div className="system-block-head text-caption">
          This project
          <span className="system-block-value tabular-nums" data-testid="project-total">
            {project && project.total_bytes > 0 ? bytes(project.total_bytes) : project?.scanning ? "scanning…" : "—"}
          </span>
        </div>
        <Meter segments={projectBands} testId="project-kinds-meter" />
        <p className="system-note text-caption tabular-nums">
          {share !== null ? `${share.toFixed(1)} % of the system disk · ` : ""}
          <span data-testid="storage-age">{scanAgeLabel(project, now)}</span>
          <IconButton
            aria-label="Rescan project storage"
            size="sm"
            icon={<RefreshCw size={12} />}
            // `IconButton` has no `loading`: the spin is the icon's own, so the button stays a
            // 20px icon rather than growing a spinner and reflowing the line it sits in.
            className={rescan.isPending || project?.scanning ? "system-rescan is-scanning" : "system-rescan"}
            disabled={rescan.isPending || project?.scanning === true}
            onClick={() => rescan.mutate()}
          />
        </p>

        {(project?.kinds?.length ?? 0) > 0 && (
          <>
            <button
              type="button"
              className="system-disclosure text-caption"
              aria-expanded={showKinds}
              data-testid="storage-kinds-toggle"
              onClick={() => setShowKinds((v) => !v)}
            >
              <ChevronRight size={11} className="system-disclosure-chevron" aria-hidden />
              By kind
              <span className="system-block-value tabular-nums">{project!.kinds!.length}</span>
            </button>
            {showKinds && (
              <table className="system-mini" data-testid="storage-kinds">
                <tbody>
                  {[...project!.kinds!]
                    .sort((a, b) => b.bytes - a.bytes)
                    .map((k) => (
                      <tr key={k.kind}>
                        <td className="system-mini-ellipsis">{k.label}</td>
                        <td className="system-mini-num system-mini-dim tabular-nums">{k.files}</td>
                        <td className="system-mini-num tabular-nums">{bytes(k.bytes)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
            {showKinds && (project?.largest?.length ?? 0) > 0 && (
              <table className="system-mini" data-testid="storage-largest">
                <tbody>
                  {project!.largest!.slice(0, 3).map((i) => (
                    <tr key={i.name}>
                      <td className="system-mini-dim system-mini-ellipsis">{i.name}</td>
                      <td className="system-mini-num tabular-nums">{bytes(i.bytes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
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
