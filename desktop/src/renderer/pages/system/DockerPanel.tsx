/**
 * Docker health, Docker-Desktop-shaped: is the daemon there, what is it holding, what is *our*
 * container, and what is running beside us.
 *
 * The reason this panel exists rather than a disk figure: from inside the `tit` container
 * `/var/lib/docker` is normally not visible at all, so "Docker root: not visible" is all a
 * filesystem reading can say. `docker system df` over the socket answers the question that
 * reading was standing in for — *is Docker filling this machine's disk, and with what* — and
 * `docker inspect` of our own container answers the other half: what limits are we running under.
 */
import { Boxes, HardDrive, TriangleAlert } from "lucide-react";
import type { SystemSnapshot } from "../../api/client";
import { StatusDot } from "../../ui/Status";
import { bytes } from "../../ui/utils";
import { dockerSegments, dockerStatus, dockerTotal, limitsLabel } from "./model";
import { Meter, MeterLegend, Panel } from "./parts";

export function DockerPanel({ docker }: { docker: SystemSnapshot["docker"] | undefined }) {
  const status = dockerStatus(docker);
  const df = docker?.df ?? null;
  const own = docker?.own ?? null;
  const segments = dockerSegments(df);

  return (
    <Panel
      title={
        <>
          <Boxes size={12} aria-hidden /> Docker
        </>
      }
      aside={
        <span className="system-docker-status" data-testid="docker-status">
          <StatusDot
            kind={status.tone === "danger" ? "danger" : status.tone === "muted" ? "neutral" : "success"}
            title={status.detail}
          />
          {status.label}
        </span>
      }
      className="system-panel-docker"
      testId="system-docker"
    >
      {/* Warnings first. They were at the bottom, which in a panel that scrolls means "below the
          fold" — and a warning nobody scrolls to is not a warning. */}
      {(docker?.warnings ?? []).length > 0 && (
        <ul className="system-warnings text-caption" data-testid="docker-warnings">
          {docker!.warnings!.map((w) => (
            <li key={w}>
              <TriangleAlert size={11} aria-hidden /> {w}
            </li>
          ))}
        </ul>
      )}

      {/* Unreachable is a real state with its own copy. Zeros here would read as a healthy daemon
          holding nothing, which is the opposite of what is true. */}
      {docker && !docker.reachable ? (
        <p className="system-docker-down text-caption">
          {status.detail}. Jobs that spawn sibling containers (QSIPrep, QSIRecon) cannot run until the
          daemon is reachable.
        </p>
      ) : (
        <>
          <div className="system-block">
            <div className="system-block-head text-caption">
              <HardDrive size={11} aria-hidden /> Disk used by Docker
              <span className="system-block-value tabular-nums">{df ? bytes(dockerTotal(df)) : "—"}</span>
            </div>
            <Meter segments={segments} testId="docker-df-meter" />
            <MeterLegend segments={segments} />
            {df && (df.images_reclaimable ?? 0) > 0 && (
              <p className="system-note text-caption tabular-nums">
                {bytes(df.images_reclaimable ?? 0)} reclaimable across {df.images_count ?? 0} image
                {df.images_count === 1 ? "" : "s"}
              </p>
            )}
          </div>

          <div className="system-block">
            <div className="system-block-head text-caption">This container</div>
            {own ? (
              <dl className="system-kv" data-testid="docker-own">
                <dt>Name</dt>
                <dd>{own.name || "—"}</dd>
                <dt>Image</dt>
                <dd className="mono system-kv-wrap">{own.image || "—"}</dd>
                <dt>Status</dt>
                <dd>
                  {own.status || own.state || "—"}
                  {own.health ? ` · ${own.health}` : ""}
                  {(own.restarts ?? 0) > 0 ? ` · ${own.restarts} restart${own.restarts === 1 ? "" : "s"}` : ""}
                </dd>
                <dt>Limits</dt>
                {/* Mounts are in Storage, not here: a bind mount is a filesystem fact, and
                    repeating it in two panels is two places to keep true. */}
                <dd className="tabular-nums">{limitsLabel(own)}</dd>
              </dl>
            ) : (
              <p className="system-note text-caption">
                The server is not running in a container — there is nothing to inspect.
              </p>
            )}
          </div>

          <div className="system-block">
            <div className="system-block-head text-caption">
              Sibling containers
              <span className="system-block-value tabular-nums">{docker?.containers?.length ?? 0}</span>
            </div>
            {(docker?.containers ?? []).length === 0 ? (
              <p className="system-note text-caption">
                None. QSIPrep and QSIRecon appear here while a diffusion job runs.
              </p>
            ) : (
              <table className="system-mini" data-testid="docker-siblings">
                <tbody>
                  {docker!.containers!.map((c) => (
                    <tr key={c.id}>
                      <td className="system-mini-dot">
                        <StatusDot kind={c.state === "running" ? "success" : "neutral"} title={c.state} />
                      </td>
                      <td className="system-mini-strong">{c.name}</td>
                      <td className="system-mini-dim mono">{c.image}</td>
                      <td className="system-mini-dim">{c.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {(docker?.images ?? []).length > 0 && (
            <div className="system-block">
              <div className="system-block-head text-caption">Largest images</div>
              <table className="system-mini" data-testid="docker-images">
                <tbody>
                  {docker!.images!.slice(0, 4).map((img) => (
                    <tr key={img.repo_tag}>
                      <td className="mono system-mini-ellipsis">{img.repo_tag}</td>
                      <td className="system-mini-num tabular-nums">{bytes(img.size)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

    </Panel>
  );
}
