/**
 * **Settings → Viewer** — the managed Tetravox install, and the one path override that overrides
 * it (V3, extended by V6: `dev/notes/v3-native-panes-external-viewer/TI.md`).
 *
 * V3 made this card a status readout with a download *link*: the user was told to go and install
 * Tetravox themselves. V6 removes that requirement — TI-Toolbox installs and maintains the viewer
 * on the host itself — so the card's job changed with it. It now shows what this app put on the
 * machine and lets a person act on it:
 *
 * - **which version is installed**, and that TI-Toolbox is the one that installed it,
 * - **when it last looked** for a newer one, and a button to look now,
 * - **how much disk it uses**, and a button to remove it,
 * - **a path override**, for a copy the user would rather this app used,
 * - **live progress** while a download runs, because 130 MB is long enough to need one.
 *
 * Three properties, stated because losing any of them quietly would be easy:
 *
 * 1. **Nothing here reaches the network on mount.** The status is a filesystem fact read through
 *    `window.tit.viewer.probe`. The network is touched only when the user presses *Check for
 *    updates*, or by the once-a-day background check main runs on its own.
 * 2. **"Not installed" is a normal state, not an error**, and it is now a temporary one: the
 *    Viewer page's own Open installs it. The button here is a convenience, not the only route.
 * 3. **Browser mode is unchanged.** There is no `window.tit`, so nothing on this host can be seen
 *    or installed; the page says so and the Viewer page downloads scene files instead.
 */
import { useState } from "react";
import { Download, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "../../ui/Button";
import { Callout, DefinitionList } from "../../ui/Feedback";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Chip } from "../../ui/Status";
import { useTetravox } from "../_shared/viewer/useTetravox";
import type { TitViewerEvent } from "../../../shared/tit-bridge";

const FALLBACK_DOWNLOAD = "https://github.com/idossha/tetravox/releases/latest";

const SOURCE_LABEL: Record<string, string> = {
  managed: "Installed by TI-Toolbox",
  discovered: "Found on this computer",
  override: "Set below",
};

/** Bytes as the one unit a person reads at this size. `0` is rendered as a dash, not "0 B". */
export function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${Math.round(bytes / (1024 * 1024))} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

/** An ISO timestamp as the local date and time, or "Never". */
export function formatChecked(iso: string | null): string {
  if (!iso) return "Never";
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? "Never" : when.toLocaleString();
}

/** One sentence for whatever the install is doing, so the card never shows a bare spinner. */
export function progressLabel(event: TitViewerEvent | null): string | null {
  if (!event) return null;
  switch (event.phase) {
    case "checking":
      return "Looking for the newest version…";
    case "downloading":
      return event.total > 0
        ? `Downloading Tetravox ${event.version} — ${Math.round((event.received / event.total) * 100)}%`
        : `Downloading Tetravox ${event.version}…`;
    case "verifying":
      return `Checking the download of ${event.version}…`;
    case "installing":
      return `Installing Tetravox ${event.version}…`;
    case "done":
      return null;
    case "error":
      return event.message;
  }
}

export function ViewerCard() {
  const tetravox = useTetravox();
  const info = tetravox.info;
  const [draftPath, setDraftPath] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const override = draftPath ?? info?.override ?? "";
  const downloadUrl = info?.downloadUrl ?? FALLBACK_DOWNLOAD;
  const managed = info?.managed;
  const busy = managed?.busy === true || tetravox.progress !== null;
  const status = progressLabel(tetravox.progress) ?? failure;

  const openDownload = (): void => void window.tit?.openExternal(downloadUrl);

  const install = async (): Promise<void> => {
    setFailure(null);
    const result = await tetravox.install();
    if (!result.ok) setFailure(result.reason);
  };

  return (
    <Card>
      <CardHeader
        title="Viewer"
        actions={
          tetravox.mode === "electron" ? (
            <Button size="sm" variant="ghost" icon={<RefreshCw size={14} />} onClick={tetravox.refresh} data-testid="viewer-card-refresh">
              Re-check
            </Button>
          ) : undefined
        }
      />
      <CardBody>
        <div data-testid="viewer-card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          <p className="field-help">
            3D viewing is the <strong>Tetravox</strong> desktop app. TI-Toolbox installs and updates it for you — you do not have to download
            anything, and the toolbox does not have to be released when the viewer changes.
          </p>

          {tetravox.mode === "browser" ? (
            // `Callout` and `Chip` render their own markup and take no `data-testid`, so the
            // hook for a spec is a wrapper here rather than a prop threaded through the UI kit.
            <div data-testid="viewer-card-browser">
              <Callout kind="info">
                Running in a browser, so this page cannot see or install anything on your computer. The Viewer page downloads a scene file,
                which you open in Tetravox with File ▸ Open Scene…
              </Callout>
            </div>
          ) : info === null ? (
            <p className="field-help">Checking…</p>
          ) : info.available ? (
            <DefinitionList
              entries={[
                [
                  "Status",
                  <span key="s" data-testid="viewer-card-status">
                    <Chip kind="success">Installed</Chip>
                  </span>,
                ],
                ["Path", <span key="p" className="mono" data-testid="viewer-card-path">{info.path}</span>],
                ["Version", <span key="v" data-testid="viewer-card-version">{info.version ?? "—"}</span>],
                ["Source", <span key="f" data-testid="viewer-card-source">{SOURCE_LABEL[info.source ?? ""] ?? "—"}</span>],
                ["Last checked", <span key="c" data-testid="viewer-card-checked">{formatChecked(managed?.lastCheckedAt ?? null)}</span>],
                ["Disk", <span key="d" data-testid="viewer-card-disk">{formatBytes(managed?.bytes ?? 0)}</span>],
                ...(managed?.pending
                  ? ([
                      [
                        "Update ready",
                        <span key="u" data-testid="viewer-card-pending">
                          {managed.pending} — it opens the next time you start TI-Toolbox
                        </span>,
                      ],
                    ] as [string, React.ReactNode][])
                  : []),
              ]}
            />
          ) : managed?.supported === false ? (
            <div data-testid="viewer-card-unsupported">
              <Callout kind="warning">
                Tetravox publishes no build for this platform, so TI-Toolbox cannot install it here. The Viewer page still writes scene files
                you can open elsewhere.
              </Callout>
            </div>
          ) : (
            <div data-testid="viewer-card-missing">
              <Callout kind="info">
                <p>Tetravox is not installed yet. It downloads by itself the first time you open a scene, or you can get it now.</p>
                <Button
                  variant="primary"
                  size="sm"
                  icon={<Download size={14} />}
                  onClick={() => void install()}
                  disabled={busy}
                  data-testid="viewer-card-install"
                  style={{ marginTop: "var(--space-2)" }}
                >
                  {busy ? "Installing…" : "Install Tetravox"}
                </Button>
              </Callout>
            </div>
          )}

          {status !== null && (
            <p className="field-help" data-testid="viewer-card-progress">
              {status}
            </p>
          )}

          {tetravox.mode === "electron" && managed?.supported && (
            <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
              <Button
                size="sm"
                variant="secondary"
                icon={<RefreshCw size={14} />}
                disabled={busy}
                onClick={() => void tetravox.checkUpdates()}
                data-testid="viewer-card-check-updates"
              >
                Check for updates
              </Button>
              {managed.version !== null && (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Trash2 size={14} />}
                  disabled={busy}
                  onClick={() => void tetravox.remove()}
                  data-testid="viewer-card-remove"
                >
                  Remove
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={openDownload} data-testid="viewer-card-download">
                Releases…
              </Button>
            </div>
          )}

          {tetravox.mode === "electron" && (
            <label className="field" data-testid="viewer-card-override">
              <span className="field-label">Use a different Tetravox…</span>
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <input
                  className="input mono"
                  type="text"
                  value={override}
                  placeholder={info?.path ?? "/Applications/Tetravox.app"}
                  onChange={(e) => setDraftPath(e.target.value)}
                  aria-label="Tetravox application path"
                  data-testid="viewer-card-override-input"
                />
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    void tetravox.setPath(override);
                    setDraftPath(null);
                  }}
                  data-testid="viewer-card-override-save"
                >
                  Use this
                </Button>
              </div>
              <span className="field-help">
                Leave empty to use the copy TI-Toolbox manages. Set it for a build of your own, or a second copy you want this app to open.
              </span>
            </label>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
