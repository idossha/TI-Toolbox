/**
 * Docker health, Docker-Desktop-shaped: is the daemon there, what container are *we*, and what is
 * running beside us.
 *
 * What this card deliberately does **not** hold is the disk accounting. `docker system df` answers
 * "what is filling this machine's disk", which is Storage's question, so the bar lives there
 * (`METRIC_HOME`) and this card is about the daemon and the container. The largest-images list is
 * behind a disclosure: it is a "why is Docker holding 200 GB" follow-up, not something to spend
 * four rows of a column on by default.
 */
import { useState } from "react";
import { Boxes, ChevronRight, TriangleAlert } from "lucide-react";
import type { SystemSnapshot } from "../../api/client";
import { StatusDot } from "../../ui/Status";
import { bytes } from "../../ui/utils";
import { dockerStatus, limitsLabel, metricsOf } from "./model";
import { Panel } from "./parts";

export function DockerPanel({ docker }: { docker: SystemSnapshot["docker"] | undefined }) {
  const [showImages, setShowImages] = useState(false);
  const status = dockerStatus(docker);
  const own = docker?.own ?? null;
  const siblings = docker?.containers ?? [];
  const images = docker?.images ?? [];
  // Docker's disk warnings are Storage's (that is where the figure they refer to is); anything
  // else — a restart loop, a container near its memory limit — belongs here.
  const warnings = (docker?.warnings ?? []).filter((w) => !w.includes("prune"));

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
      testId="system-docker"
      metrics={metricsOf("docker")}
    >
      {warnings.length > 0 && (
        <ul className="system-warnings text-caption" data-testid="docker-warnings">
          {warnings.map((w) => (
            <li key={w}>
              <TriangleAlert size={11} aria-hidden /> {w}
            </li>
          ))}
        </ul>
      )}

      {/* Unreachable is a real state with its own copy. Zeros would read as a healthy daemon
          holding nothing, which is the opposite of what is true. */}
      {docker && !docker.reachable ? (
        <p className="system-docker-down text-caption">
          {status.detail}. Jobs that spawn sibling containers (QSIPrep, QSIRecon) cannot run until the
          daemon is reachable.
        </p>
      ) : (
        <>
          {own ? (
            <dl className="system-kv" data-testid="docker-own">
              <dt>Container</dt>
              <dd>{own.name || "—"}</dd>
              <dt>Image</dt>
              <dd className="mono">{own.image || "—"}</dd>
              <dt>Status</dt>
              <dd>
                {own.status || own.state || "—"}
                {own.health ? ` · ${own.health}` : ""}
                {(own.restarts ?? 0) > 0 ? ` · ${own.restarts} restart${own.restarts === 1 ? "" : "s"}` : ""}
              </dd>
              <dt>Limits</dt>
              <dd className="tabular-nums">{limitsLabel(own)}</dd>
              <dt>Mounts</dt>
              <dd className="mono system-kv-wrap">
                {(own.mounts ?? []).length > 0
                  ? own.mounts!.map((m) => `${m.destination} (${m.mode || "rw"})`).join(", ")
                  : "—"}
              </dd>
            </dl>
          ) : (
            <p className="system-note text-caption">
              The server is not running in a container — there is nothing to inspect.
            </p>
          )}

          <div className="system-block">
            <div className="system-block-head text-caption">
              Siblings
              <span className="system-block-value tabular-nums">{siblings.length}</span>
            </div>
            {siblings.length === 0 ? (
              <p className="system-note text-caption">QSIPrep and QSIRecon appear here while a diffusion job runs.</p>
            ) : (
              <table className="system-mini" data-testid="docker-siblings">
                <tbody>
                  {siblings.map((c) => (
                    <tr key={c.id}>
                      <td className="system-mini-dot">
                        <StatusDot kind={c.state === "running" ? "success" : "neutral"} title={c.state} />
                      </td>
                      <td className="system-mini-strong system-mini-ellipsis">{c.name}</td>
                      <td className="system-mini-dim">{c.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {images.length > 0 && (
            <div className="system-block">
              <button
                type="button"
                className="system-disclosure text-caption"
                aria-expanded={showImages}
                data-testid="docker-images-toggle"
                onClick={() => setShowImages((v) => !v)}
              >
                <ChevronRight size={11} className="system-disclosure-chevron" aria-hidden />
                Images
                <span className="system-block-value tabular-nums">{images.length}</span>
              </button>
              {showImages && (
                <table className="system-mini" data-testid="docker-images">
                  <tbody>
                    {images.map((img) => (
                      <tr key={img.repo_tag}>
                        <td className="mono system-mini-ellipsis">{img.repo_tag}</td>
                        <td className="system-mini-num tabular-nums">{bytes(img.size)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
