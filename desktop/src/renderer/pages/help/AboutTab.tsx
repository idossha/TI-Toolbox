import { useQuery } from "@tanstack/react-query";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Callout, DefinitionList, Skeleton } from "../../ui/Feedback";
import { isElectron } from "../../env";
import { getVersion } from "./api";
import { ExternalLinkButton } from "./links";

export function AboutTab() {
  const version = useQuery({ queryKey: ["help-version"], queryFn: getVersion });
  const desktopVersion = useQuery({ queryKey: ["desktop-version"], queryFn: () => window.tit!.appVersion(), enabled: isElectron });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <Card>
        <CardHeader title="TI-Toolbox" />
        <CardBody>
          {version.isPending && <Skeleton height={60} />}
          {version.error && <Callout kind="danger">Could not load the server version.</Callout>}
          {version.data && (
            <DefinitionList
              entries={[
                ["App", isElectron ? `Electron desktop (${window.tit!.platform()})` : "Browser"],
                ...(isElectron ? ([["Desktop version", desktopVersion.data ?? "…"]] as [string, string][]) : []),
                ["Image (tit)", version.data.tit_version],
                ["SimNIBS", version.data.simnibs ?? "not available"],
              ]}
            />
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Updates" />
        <CardBody>
          <Callout kind="info">
            Automatic update checks aren't wired up yet in v3 — the toolbox ships as a Docker image, so updating means{" "}
            <code className="mono">docker compose pull</code>. Check the release notes for what's new.
          </Callout>
          <div style={{ marginTop: "var(--space-3)" }}>
            <ExternalLinkButton href="https://github.com/idossha/TI-Toolbox/releases">View releases</ExternalLinkButton>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
