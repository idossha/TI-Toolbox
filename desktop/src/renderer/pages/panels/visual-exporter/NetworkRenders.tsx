import { useMemo } from "react";
import type { SimulationNetworks } from "./api";

type Render = SimulationNetworks["renders"][number];

/** One same-origin raw URL per render; the version makes a re-render replace the cached file. */
function rawUrl(path: string, version: string): string {
  return `/api/files/raw${path.split("/").map(encodeURIComponent).join("/")}?v=${encodeURIComponent(version)}`;
}

const COLOURS: Record<string, string> = { ti_max: "TI_max", ti_along: "ti_along", ti_ratio: "ti_ratio", align_index: "align_index", direction: "Fibre direction" };

/** What a render shows, in words: a colour's figure has no view, and an older folder's stills do. */
export function renderLabel(render: Pick<Render, "colour" | "view">): string {
  const colour = COLOURS[render.colour] ?? render.colour;
  return render.view ? `${colour} · ${render.view}` : colour;
}

/** A figure or a video, drawn in the grid; a network's `.blend` is a link under it. */
export const isPicture = (render: Pick<Render, "kind">): boolean => render.kind !== "scene";

/** Each network's renders together, the most recently rendered network first. */
export function groupRenders(renders: readonly Render[]): { network: string; renders: Render[] }[] {
  const groups = new Map<string, Render[]>();
  for (const render of renders) groups.set(render.network, [...(groups.get(render.network) ?? []), render]);
  const labelled = (a: Render, b: Render) => renderLabel(a).localeCompare(renderLabel(b));
  return [...groups].map(([network, rows]) => ({ network, renders: [...rows].sort(labelled) }));
}

/**
 * A simulation's renders by network, one open at a time by default (the chosen one, else the newest),
 * so a big set does not saturate the page.
 */
export function NetworkRenders({ renders, current }: { renders: SimulationNetworks["renders"]; current?: string }) {
  const groups = useMemo(() => groupRenders(renders), [renders]);
  if (renders.length === 0) return <p className="field-help">Rendered figures and videos of this simulation appear here.</p>;
  const open = groups.some((group) => group.network === current) ? current : groups[0]!.network;
  return (
    <div className="network-render-groups" data-testid="network-renders">
      {groups.map((group) => (
        <details key={group.network} open={group.network === open} data-network={group.network}>
          <summary>
            {group.network} <span className="field-help tabular">{group.renders.filter(isPicture).length}</span>
          </summary>
          <div className="network-renders">
            {group.renders.filter(isPicture).map((render) => (
              <figure key={render.path}>
                {render.kind === "video" ? (
                  <video src={rawUrl(render.path, render.modified_at)} controls preload="metadata" aria-label={`${group.network}, ${renderLabel(render)}`} />
                ) : (
                  <a href={rawUrl(render.path, render.modified_at)} target="_blank" rel="noreferrer">
                    <img src={rawUrl(render.path, render.modified_at)} alt={`${group.network}, ${renderLabel(render)}`} loading="lazy" />
                  </a>
                )}
                <figcaption>{renderLabel(render)}</figcaption>
              </figure>
            ))}
          </div>
          {group.renders.filter((render) => !isPicture(render)).map((render) => (
            <p key={render.path} className="field-help">
              Blender scene: <a href={rawUrl(render.path, render.modified_at)} download={render.name}>{render.name}</a>
            </p>
          ))}
        </details>
      ))}
    </div>
  );
}
