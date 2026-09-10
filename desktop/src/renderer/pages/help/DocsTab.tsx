import { useQuery } from "@tanstack/react-query";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Callout, Skeleton } from "../../ui/Feedback";
import { ExternalLinkButton } from "./links";
import { DOCS_SITE, docsSiteReachable } from "./api";

const LINKS: { label: string; href: string }[] = [
  { label: "Open documentation in browser", href: DOCS_SITE },
  { label: "Troubleshooting", href: `${DOCS_SITE}wiki/troubleshooting/` },
  { label: "GitHub repository", href: "https://github.com/idossha/TI-Toolbox" },
];

/**
 * The published documentation site, in an iframe.
 *
 * It deliberately does **not** iframe anything on the app's own origin: `tit.server`'s static
 * route is an SPA catch-all (`tit/server/static.py` — only `api`/`ws`/`auth`/`tetravox` are
 * reserved), so a same-origin path like `/docs/` answers 200 with the app's own `index.html` and
 * the tab ends up rendering TI-Toolbox inside TI-Toolbox. The site is the single source of the
 * docs anyway; `frame-src` in `tit/server/app.py` allows exactly this origin.
 */
export function DocsTab() {
  const reachable = useQuery({ queryKey: ["docs-site-reachable"], queryFn: () => docsSiteReachable(), retry: false });

  if (reachable.isPending) return <Skeleton height={300} />;

  if (reachable.data) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <ExternalLinkButton href={DOCS_SITE}>Open in browser</ExternalLinkButton>
        </div>
        <iframe
          data-testid="docs-frame"
          title="TI-Toolbox documentation"
          src={DOCS_SITE}
          style={{ width: "100%", height: "70vh", border: "1px solid var(--line)", borderRadius: "var(--radius-card)", background: "var(--surface)" }}
        />
      </div>
    );
  }

  return (
    <Card>
      <CardHeader title="Documentation" />
      <CardBody>
        <Callout kind="info">
          The documentation website couldn&apos;t be reached — this machine looks offline. Open{" "}
          {DOCS_SITE} from a connected machine for the full guides, wiki and troubleshooting notes.
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
