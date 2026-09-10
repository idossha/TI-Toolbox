/**
 * The viewer pane: one `<iframe>` onto the Tetravox embed, and the states that can cover it.
 *
 * The embed is a released Tetravox artifact installed into the container image at
 * `/opt/tetravox/embed` and served by `tit.server` under `/tetravox/` with its own CSP
 * (`docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)` D1/D3). TI owns the frame, the protocol types and the
 * scene; it owns no rendering code at all.
 *
 * The iframe itself, its sandbox flags and its teardown are `viewer/EmbedFrame.tsx`, shared with
 * the run pages' scene panes — that file's header carries the sandbox rationale. What is left here
 * is the Viewer page's own chrome: the loading rows and the three states that can cover the frame.
 */
import { Button } from "../ui/Button";
import { EmbedFrame } from "./EmbedFrame";
import { HANDSHAKE_TIMEOUT_MS, useViewerStore } from "./store";
import "./viewer.css";

export interface TetravoxFrameProps {
  /**
   * The origin the embed is served from — this app's own. Defaults to `window.location.origin`;
   * passed explicitly only by tests.
   */
  origin?: string;
  /** Overrides the handshake timeout. Tests use a short one; nothing else should set it. */
  handshakeTimeoutMs?: number;
  /** Shown in the `no-embed` state so the message names a version someone can act on. */
  embedVersion?: string | null;
  className?: string;
  /**
   * Bumped by the host to force a full remount of the iframe — the only way to recover from a
   * frame that mounted and never answered (DESIGN.md §10's `no-embed` state). The source bar's
   * reload `IconButton` and this component's own "Reload viewer" button both drive the same value.
   */
  reloadToken?: number;
  /** Wired to the `no-embed` state's own "Reload viewer" button; same effect as `reloadToken`. */
  onReload?: () => void;
}

/** A byte count as the loading rows show it. Empty until the loader reports a size. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function TetravoxFrame({
  origin,
  handshakeTimeoutMs = HANDSHAKE_TIMEOUT_MS,
  embedVersion,
  className,
  reloadToken = 0,
  onReload,
}: TetravoxFrameProps) {
  const status = useViewerStore((s) => s.status);
  const error = useViewerStore((s) => s.error);
  const renderer = useViewerStore((s) => s.renderer);
  const progress = useViewerStore((s) => s.progress);
  const connect = useViewerStore((s) => s.connect);
  const disconnect = useViewerStore((s) => s.disconnect);
  const layers = useViewerStore((s) => s.layers);

  const loading = status === "loading" && progress.length > 0;

  /**
   * `volume:-,surface:annotation` — what the **engine** says it is drawing, not what we sent it.
   *
   * The one observable that can catch a surface whose attachment did not take. A sidecar the
   * embed could not fetch yields a solid-coloured surface and a perfectly successful `loaded`
   * event: the geometry is there, nothing errors, and the picture is simply missing the
   * parcellation that was the whole reason for ticking it. `colorMode` on the `layers` event is
   * the only place that difference shows, so it is put where a test can read it.
   */
  const layerKinds = layers
    .map((layer) => `${layer.kind ?? "?"}:${(layer as { colorMode?: string }).colorMode ?? "-"}`)
    .join(",");

  return (
    <div className={className ? `tvx-host ${className}` : "tvx-host"} data-testid="tetravox-host" data-viewer-status={status} data-renderer={renderer ?? ""} data-viewer-layer-kinds={layerKinds}>
      <EmbedFrame
        origin={origin}
        connect={connect}
        disconnect={disconnect}
        handshakeTimeoutMs={handshakeTimeoutMs}
        reloadToken={reloadToken}
        className="tvx-frame"
        testId="tetravox-frame"
        title="Tetravox viewer"
      />

      {loading && (
        <div className="tvx-overlay">
          <ul className="tvx-loadlist" data-testid="viewer-progress">
            {progress.map((row) => (
              <li key={row.id} className="tvx-loadrow">
                <span className="tvx-loadname">{row.name}</span>
                <span className="tvx-loadmeta">
                  {row.phase}
                  {row.bytes > 0 ? ` · ${formatBytes(row.bytes)}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {status === "no-webgl2" && (
        <div className="tvx-state" data-testid="viewer-no-webgl2">
          <div className="tvx-state-body">
            <p className="tvx-state-title">This machine cannot run the 3D viewer</p>
            <p className="tvx-state-text">
              The viewer needs WebGL2 and this window has no context{renderer ? ` (renderer: ${renderer})` : ""}. Chromium removed its software
              fallback in M137, so there is nothing to switch on — the usual cause is a graphics driver on the browser&apos;s blocklist, or a
              remote session with no GPU. Everything else in TI-Toolbox works; only rendering is unavailable.
            </p>
          </div>
        </div>
      )}

      {status === "no-embed" && (
        <div className="tvx-state" data-testid="viewer-no-embed">
          <div className="tvx-state-body">
            {/* Deliberately NOT the Viewer page's "no viewer bundle" wording: that state is the
                server saying up front that it has no embed, this one is a frame that mounted and
                then went silent. A support screenshot cropped to one sentence has to tell them
                apart, so this one leads with the timeout and names the seconds. */}
            <p className="tvx-state-title">The viewer did not answer</p>
            <p className="tvx-state-text">
              The frame at <code>/tetravox/</code> mounted but said nothing for {Math.round(handshakeTimeoutMs / 1000)} s
              {embedVersion ? `, though the server reports embed ${embedVersion}` : ""}. A bundle that is present but failed to start looks like
              this, and so does one that is missing from a server started without <code>TIT_TETRAVOX_EMBED_DIR</code>. If it stays quiet after a
              reload, check the container logs and rebuild or pull the image.
            </p>
            {onReload && (
              <div className="tvx-state-actions">
                <Button variant="secondary" size="sm" onClick={onReload}>
                  Reload viewer
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {status === "error" && error !== null && (
        <div className="tvx-scene-error" data-testid="viewer-error" role="alert">
          <div className="tvx-state-body">
            <p className="tvx-state-title">Some scene data could not be loaded</p>
            <p className="tvx-state-text">{error}</p>
            {onReload && (
              <div className="tvx-state-actions">
                <Button variant="secondary" size="sm" onClick={onReload}>
                  Retry scene
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
