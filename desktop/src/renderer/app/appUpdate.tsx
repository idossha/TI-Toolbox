/**
 * TI-Toolbox's own update notice: the nav rail's version label, the once-per-session popup, and
 * the Settings ▸ Updates card. One query (`["app-update"]`) feeds all three; main asks GitHub once
 * per app process (`src/main/updates.ts`), so mounting these anywhere costs no extra requests.
 * Browser sessions have no bridge: the label shows the server's `tit_version` and nothing checks.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Download, RefreshCw } from "lucide-react";
import type { TitAppUpdate } from "../../shared/tit-bridge";
import { getVersion } from "../api/client";
import { isProjectHome } from "../env";
import { Button } from "../ui/Button";
import { DefinitionList } from "../ui/Feedback";
import { Card, CardBody, CardHeader } from "../ui/Layout";
import { Dialog, Tooltip } from "../ui/Overlay";
import { Chip, StatusDot } from "../ui/Status";

const UPDATE_KEY = ["app-update"];
const canCheck = () => typeof window.tit?.checkAppUpdate === "function";

export function useAppUpdate() {
  return useQuery({
    queryKey: UPDATE_KEY,
    queryFn: () => window.tit!.checkAppUpdate!(false),
    enabled: canCheck(),
    staleTime: Infinity,
    retry: false,
  });
}

function download(update: TitAppUpdate | undefined): void {
  if (update?.url) void window.tit?.openExternal(update.url);
}

/** "TI-Toolbox X is available" — at most once per app process (main sets `prompt` once). */
export function AppUpdatePrompt() {
  const update = useAppUpdate().data;
  const [dismissed, setDismissed] = useState(false);
  if (!update?.prompt || !update.available) return null;
  return (
    <Dialog
      open={!dismissed}
      onOpenChange={(open) => setDismissed(!open)}
      title="Update available"
      description={`TI-Toolbox ${update.latest} is available (you have ${update.current}).`}
      footer={
        <>
          <Button variant="secondary" data-testid="app-update-later" onClick={() => setDismissed(true)}>
            Later
          </Button>
          <Button
            variant="primary"
            icon={<Download size={14} aria-hidden />}
            data-testid="app-update-download"
            onClick={() => {
              download(update);
              setDismissed(true);
            }}
          >
            Download
          </Button>
        </>
      }
    >
      <p className="text-body" style={{ margin: 0, color: "var(--ink-2)" }}>
        Download the new installer from the release page and install it over this version. Your projects and settings are kept.
      </p>
    </Dialog>
  );
}

/** The nav rail footer: always the version; a dot and a link to Settings ▸ Updates when one is out. */
export function AppVersionLabel() {
  const navigate = useNavigate();
  const update = useAppUpdate().data;
  const desktop = window.tit !== undefined;
  const serverVersion = useQuery({ queryKey: ["version"], queryFn: () => getVersion(), enabled: !desktop });
  const desktopVersion = useQuery({ queryKey: ["desktop-version"], queryFn: () => window.tit!.appVersion(), enabled: desktop && !canCheck() });
  const version = update?.current ?? desktopVersion.data ?? serverVersion.data?.tit_version;
  if (!version) return null;
  if (!update?.available) {
    return (
      <div className="nav-version" data-testid="nav-app-version">
        <span className="nav-version-v">v</span>
        {version}
      </div>
    );
  }
  const label = `TI-Toolbox ${update.latest} is available`;
  return (
    <Tooltip label={label}>
      <button
        type="button"
        className="nav-version nav-version-update"
        data-testid="nav-app-version"
        data-update="available"
        aria-label={`${label} (you have ${version})`}
        // Settings is unreachable before a project is open, so the project home downloads directly.
        onClick={() => (isProjectHome ? download(update) : navigate({ pathname: "/settings", hash: "#updates" }))}
      >
        <StatusDot kind="accent" />
        <span className="nav-version-v">v</span>
        {version}
      </button>
    </Tooltip>
  );
}

/** Settings ▸ Updates and Help ▸ About: installed, latest, status, Check again. Desktop only. */
export function AppUpdateCard() {
  const queryClient = useQueryClient();
  const query = useAppUpdate();
  const recheck = useMutation({
    mutationFn: () => window.tit!.checkAppUpdate!(true),
    onSuccess: (result) => queryClient.setQueryData(UPDATE_KEY, result),
  });
  const update = query.data;
  const checking = query.isFetching || recheck.isPending;
  const status = !update ? (
    <span className="field-help">{checking ? "Checking…" : "Not available in this version of the app."}</span>
  ) : update.error ? (
    <Chip kind="warning" dot>Couldn't check</Chip>
  ) : update.available ? (
    <Chip kind="accent" dot>Update available</Chip>
  ) : (
    <Chip kind="success" dot>Up to date</Chip>
  );
  return (
    <Card>
      <CardHeader title="TI-Toolbox updates" />
      <CardBody>
        <div data-testid="app-update-card" data-status={update ? (update.error ? "error" : update.available ? "available" : "current") : "unknown"}>
          <DefinitionList
            entries={[
              ["Installed", update?.current ?? "…"],
              ["Latest release", update?.latest ?? "—"],
              ["Status", status],
            ]}
          />
          {update?.error && <p className="field-help" style={{ marginTop: "var(--space-2)" }}>{update.error}</p>}
          {update?.available && (
            <p className="field-help" style={{ marginTop: "var(--space-2)" }}>
              Download the new installer from the release page and install it over this version. Your projects and settings are kept.
            </p>
          )}
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
            {update?.available && update.url && (
              <Button variant="primary" size="sm" icon={<Download size={12} aria-hidden />} onClick={() => download(update)} data-testid="app-update-card-download">
                Download {update.latest}
              </Button>
            )}
            {canCheck() && (
              <Button size="sm" icon={<RefreshCw size={12} aria-hidden />} loading={checking} onClick={() => recheck.mutate()} data-testid="app-update-check">
                Check again
              </Button>
            )}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
