/**
 * The ELECTRODES section every job that places electrodes shows: shape, width x height and gel
 * thickness, and a "?" that explains them with a small diagram and the SimNIBS reference.
 *
 * One component for the Simulator's job settings and the Optimizer's Generate-leadfield step, so
 * the two cannot drift; the Flex form keeps its own fields (its electrode is a disc and it has a
 * minimum distance) but carries the same `ElectrodeHelp`.
 */
import { CircleHelp, ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { isElectron } from "../../../env";
import { Field } from "../../../ui/Field";
import { HelpBody } from "../../../ui/HelpPopover";
import { NumberInput } from "../../../ui/NumberInput";
import { Popover } from "../../../ui/Overlay";
import { SegmentedControl } from "../../../ui/SegmentedControl";
import "./electrodes.css";

export const SIMNIBS_ELECTRODE_URL = "https://simnibs.github.io/simnibs/build/html/documentation/sim_struct/electrode.html";
/** Saturnino, Antunes & Thielscher 2015, NeuroImage 120:25-35, doi:10.1016/j.neuroimage.2015.06.067. */
export const ELECTRODE_PAPER_URL = "https://www.sciencedirect.com/science/article/pii/S1053811915005728";

/** Paraphrased from the SimNIBS ELECTRODE reference (`shape`, `dimensions`, `thickness`). */
const HELP = `**Shape** — an ellipse or a rectangle. An ellipse with equal width and height is a round electrode.

**Dimensions** — the electrode's width × height in mm, along its own two axes.

**Gel thickness** — the layer of saline gel between the skin and the rubber, in mm.

**Rubber** — the conductive silicone-rubber pad on top of the gel, 2 mm here.

SimNIBS builds each electrode as these two layers, rubber on saline gel. Its size and its gel change the field under and around it.`;

/** The geometry the section edits — the Simulator's `JobSettings` names. */
export interface ElectrodeGeometry {
  electrodeShape: "ellipse" | "rect";
  dimensions: [number, number];
  gelThickness: number;
}

/** A link that opens in the system browser: `openExternal` in the app, a new tab in a browser. */
function External({ href, children }: { href: string; children: ReactNode }) {
  const body = (
    <>
      {children} <ExternalLink size={10} aria-hidden />
    </>
  );
  return isElectron ? (
    <button type="button" className="help-more electrode-help-link" data-href={href} onClick={() => void window.tit?.openExternal(href)}>
      {body}
    </button>
  ) : (
    <a className="help-more electrode-help-link" href={href} target="_blank" rel="noreferrer" data-href={href}>
      {body}
    </a>
  );
}

/** Skin, then gel, then rubber, with the width across them — not to scale. */
function ElectrodeDiagram() {
  return (
    <svg className="electrode-diagram" viewBox="0 0 280 100" role="img" aria-label="An electrode on the skin: rubber on a gel layer, width across both">
      <path className="electrode-diagram-skin" d="M0 90 Q105 70 210 90 L210 100 L0 100 Z" />
      <path className="electrode-diagram-gel" d="M40 83.8 Q105 76.2 170 83.8 L170 77.8 Q105 70.2 40 77.8 Z" />
      <path className="electrode-diagram-rubber" d="M40 77.8 Q105 70.2 170 77.8 L170 65.8 Q105 58.2 40 65.8 Z" />
      <g className="electrode-diagram-ink">
        <line x1="40" y1="48" x2="170" y2="48" />
        <line x1="40" y1="43" x2="40" y2="53" />
        <line x1="170" y1="43" x2="170" y2="53" />
        <text x="105" y="42" textAnchor="middle">width (mm)</text>
        <line x1="166" y1="69" x2="182" y2="64" />
        <text x="185" y="66">rubber</text>
        <line x1="166" y1="80" x2="182" y2="82" />
        <text x="185" y="85">gel (saline)</text>
        <text x="185" y="98">skin</text>
      </g>
    </svg>
  );
}

/** The "?" beside an ELECTRODES heading. */
export function ElectrodeHelp() {
  return (
    <Popover
      trigger={
        <button type="button" className="electrode-help-trigger" aria-label="About electrode parameters" data-help-icon data-testid="electrode-help">
          <CircleHelp size={12} aria-hidden />
        </button>
      }
    >
      <div className="help-popover electrode-help" data-testid="electrode-help-content">
        <div className="help-popover-title">Electrode parameters</div>
        <ElectrodeDiagram />
        <HelpBody text={HELP} />
        <div className="electrode-help-links">
          <External href={SIMNIBS_ELECTRODE_URL}>SimNIBS electrode reference</External>
          <External href={ELECTRODE_PAPER_URL}>Saturnino, Antunes &amp; Thielscher 2015, NeuroImage</External>
        </div>
      </div>
    </Popover>
  );
}

/** The heading, its "?", and shape · dimensions · gel thickness in one wrapping row. */
export function ElectrodeSettings({ value, onChange }: { value: ElectrodeGeometry; onChange: (next: ElectrodeGeometry) => void }) {
  const [w, h] = value.dimensions;
  return (
    <section className="electrode-settings" data-testid="electrode-settings">
      <h4 className="electrode-settings-heading">
        Electrodes <ElectrodeHelp />
      </h4>
      <div className="field-row-inline">
        <Field label="Shape">
          <SegmentedControl
            value={value.electrodeShape}
            onValueChange={(v) => onChange({ ...value, electrodeShape: v as ElectrodeGeometry["electrodeShape"] })}
            options={[
              { value: "ellipse", label: "Ellipse" },
              { value: "rect", label: "Rectangle" },
            ]}
            aria-label="Electrode shape"
          />
        </Field>
        <Field label="Dimensions">
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <NumberInput value={w} onValueChange={(v) => onChange({ ...value, dimensions: [v ?? 8, h] })} unit="w" step={0.5} min={0} aria-label="Electrode width" />
            <NumberInput value={h} onValueChange={(v) => onChange({ ...value, dimensions: [w, v ?? 8] })} unit="h" step={0.5} min={0} aria-label="Electrode height" />
          </div>
        </Field>
        <Field label="Gel thickness" className="electrode-gel-field">
          <NumberInput
            value={value.gelThickness}
            onValueChange={(v) => onChange({ ...value, gelThickness: v ?? 1 })}
            step={0.5}
            min={0}
            unit="mm"
            aria-label="Gel thickness"
          />
        </Field>
      </div>
    </section>
  );
}
