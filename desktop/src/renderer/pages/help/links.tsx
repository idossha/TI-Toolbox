import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { isElectron } from "../../env";
import { Button } from "../../ui/Button";

/** Opens an http(s) URL in the host's default browser (Electron) or a new tab (browser mode). */
export function ExternalLinkButton({ href, children }: { href: string; children: ReactNode }) {
  if (isElectron) {
    return (
      <Button variant="ghost" size="sm" icon={<ExternalLink size={12} />} onClick={() => void window.tit?.openExternal(href)}>
        {children}
      </Button>
    );
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">
      <ExternalLink size={12} aria-hidden />
      <span className="btn-label-loading">{children}</span>
    </a>
  );
}
