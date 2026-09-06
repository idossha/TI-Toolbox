/**
 * **Settings → Viewer** — where Tetravox is, and how to get it (V3,
 * `dev/notes/v3-native-panes-external-viewer-plan.md`).
 *
 * This replaces the "Viewer engine" card, which installed, activated, rolled back and removed an
 * embed bundle inside the container. All of that is gone. The viewer is now an ordinary desktop
 * application on the host: it is signed and notarised, it updates itself through
 * electron-updater, and neither its version nor its update policy is TI-Toolbox's business. What
 * is left is the one thing this app genuinely knows and the user genuinely needs:
 *
 * - **is it there**, and at which path (discovered, or the one you set),
 * - **a path override**, for a Linux AppImage outside `PATH` or a second copy,
 * - **a download link**, when it is not there.
 *
 * Two properties worth stating because they were properties of the old card too, and losing them
 * quietly would be easy:
 *
 * 1. **This card never reaches the network.** Not on mount, not on refresh. It looks at the local
 *    filesystem through `window.tit.viewer.probe`. The download link is a link — it is followed
 *    only when clicked.
 * 2. **"Not installed" is a sentence, not an error.** A machine without Tetravox is a normal
 *    state: everything else in the app works, and this card says what to do about the one thing
 *    that does not.
 *
 * In browser mode there is no `window.tit` at all, so nothing here can be answered — the card says
 * so and points at the same download page. A browser can still build scenes; it downloads them.
 */
import { useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { Button } from "../../ui/Button";
import { Callout, DefinitionList } from "../../ui/Feedback";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Chip } from "../../ui/Status";
import { useTetravox } from "../_shared/viewer/useTetravox";

const FALLBACK_DOWNLOAD = "https://github.com/idossha/tetravox/releases/latest";

const SOURCE_LABEL: Record<string, string> = {
  discovered: "Found automatically",
  override: "Set below",
};

export function ViewerCard() {
  const tetravox = useTetravox();
  const info = tetravox.info;
  const [draftPath, setDraftPath] = useState<string | null>(null);
  const override = draftPath ?? info?.override ?? "";
  const downloadUrl = info?.downloadUrl ?? FALLBACK_DOWNLOAD;

  const openDownload = (): void => void window.tit?.openExternal(downloadUrl);

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
            3D viewing is the <strong>Tetravox</strong> desktop app, a separate application that opens the scene files this toolbox writes. It
            updates itself; nothing here has to be released when it does.
          </p>

          {tetravox.mode === "browser" ? (
            <Callout kind="info" data-testid="viewer-card-browser">
              Running in a browser, so this page cannot see what is installed on your computer. The Viewer page downloads a scene file, which
              you open in Tetravox with File ▸ Open Scene…
            </Callout>
          ) : info === null ? (
            <p className="field-help">Checking…</p>
          ) : info.available ? (
            <DefinitionList
              entries={[
                [
                  "Status",
                  <Chip key="s" kind="success" data-testid="viewer-card-status">
                    Installed
                  </Chip>,
                ],
                ["Path", <span key="p" className="mono" data-testid="viewer-card-path">{info.path}</span>],
                ["Version", <span key="v" data-testid="viewer-card-version">{info.version ?? "—"}</span>],
                ["Found", SOURCE_LABEL[info.source ?? ""] ?? "—"],
              ]}
            />
          ) : (
            <Callout kind="warning" data-testid="viewer-card-missing">
              <p>Tetravox was not found on this computer, so the Viewer page cannot open anything yet.</p>
              <Button
                variant="primary"
                size="sm"
                icon={<Download size={14} />}
                onClick={openDownload}
                data-testid="viewer-card-download"
                style={{ marginTop: "var(--space-2)" }}
              >
                Download Tetravox
              </Button>
            </Callout>
          )}

          {tetravox.mode === "electron" && (
            <label className="field" data-testid="viewer-card-override">
              <span className="field-label">Application path</span>
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
                Leave empty to look in the usual places. Set it for an AppImage outside your <code className="mono">PATH</code>, or a second
                copy you want this app to use.
              </span>
            </label>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
