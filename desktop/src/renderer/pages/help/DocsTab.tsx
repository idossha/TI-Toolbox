import { useQuery } from "@tanstack/react-query";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Callout, Skeleton } from "../../ui/Feedback";
import { ExternalLinkButton } from "./links";
import { docsAvailable } from "./api";

const WIKI = "https://idossha.github.io/TI-Toolbox/wiki/";

const LINKS: { label: string; href: string }[] = [
  { label: "Full documentation (wiki)", href: WIKI },
  { label: "Troubleshooting", href: `${WIKI}troubleshooting/` },
  { label: "GitHub repository", href: "https://github.com/idossha/TI-Toolbox" },
];

export function DocsTab() {
  const docs = useQuery({ queryKey: ["docs-available"], queryFn: docsAvailable });

  if (docs.isPending) return <Skeleton height={300} />;

  if (docs.data) {
    return (
      <iframe
        title="TI-Toolbox documentation"
        src="/docs/"
        style={{ width: "100%", height: "70vh", border: "1px solid var(--line)", borderRadius: "var(--radius-card)", background: "var(--surface)" }}
      />
    );
  }

  return (
    <Card>
      <CardHeader title="Documentation" />
      <CardBody>
        <Callout kind="info">
          The offline docs bundle isn't present on this server. Use the published documentation instead — it covers the same material.
        </Callout>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-3)", alignItems: "flex-start" }}>
          {LINKS.map((l) => (
            <ExternalLinkButton key={l.href} href={l.href}>
              {l.label}
            </ExternalLinkButton>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}
