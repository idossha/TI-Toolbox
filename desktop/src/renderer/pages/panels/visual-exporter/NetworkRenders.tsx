import type { SimulationNetworks } from "./api";

/** One same-origin raw URL per render; the version makes a re-render replace the cached file. */
function rawUrl(path: string, version: string): string {
  return `/api/files/raw${path.split("/").map(encodeURIComponent).join("/")}?v=${encodeURIComponent(version)}`;
}

/** The PNG stills and MP4 videos in the simulation's `visual_exports/.../tract/`, newest first. */
export function NetworkRenders({ renders }: { renders: SimulationNetworks["renders"] }) {
  if (renders.length === 0) return <p className="field-help">Rendered stills and videos of this simulation appear here.</p>;
  return (
    <div className="network-renders" data-testid="network-renders">
      {renders.map((render) => (
        <figure key={render.path}>
          {render.kind === "video" ? (
            <video src={rawUrl(render.path, render.modified_at)} controls preload="metadata" aria-label={render.name} />
          ) : (
            <a href={rawUrl(render.path, render.modified_at)} target="_blank" rel="noreferrer">
              <img src={rawUrl(render.path, render.modified_at)} alt={render.name} loading="lazy" />
            </a>
          )}
          <figcaption>{render.name}</figcaption>
        </figure>
      ))}
    </div>
  );
}
