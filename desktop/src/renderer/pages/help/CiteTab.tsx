import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Button } from "../../ui/Button";
import { ExternalLinkButton } from "./links";

const DOI = "https://doi.org/10.1101/2025.10.06.680781";
const CITATION =
  "Haber I, Jackson A, Thielscher A, Hai A, Tononi G. Temporal Interference Toolbox: A comprehensive pipeline for transcranial electrical stimulation optimization. bioRxiv 2025.10.06.680781; https://doi.org/10.1101/2025.10.06.680781.";

export function CiteTab() {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(CITATION);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard unavailable — the citation text is still selectable on the page
    }
  }

  return (
    <Card>
      <CardHeader title="Cite TI-Toolbox" />
      <CardBody>
        <p className="text-body" style={{ color: "var(--ink-2)", marginBottom: "var(--space-3)" }}>
          If TI-Toolbox contributed to your research, please cite the paper below.
        </p>
        <p className="text-body mono" style={{ background: "var(--surface-2)", padding: "var(--space-3)", borderRadius: "var(--radius-control)" }}>
          {CITATION}
        </p>
        <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
          <Button variant="secondary" size="sm" icon={copied ? <Check size={14} /> : <Copy size={14} />} onClick={() => void copy()}>
            {copied ? "Copied" : "Copy citation"}
          </Button>
          <ExternalLinkButton href={DOI}>Open DOI</ExternalLinkButton>
        </div>
      </CardBody>
    </Card>
  );
}
