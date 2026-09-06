import { FlaskConical } from "lucide-react";
import { lazy, Suspense, type ComponentType } from "react";
import type { PageDef } from "../../app/registry";

// import.meta.env.DEV covers `electron-vite dev`. A real `electron-vite build` always sets
// NODE_ENV=production internally regardless of any `--mode` flag (electron-vite's own build
// command hardcodes it — see desktop/README.md), so a *built* app that still wants the gallery
// (screenshot QA in CI) opts in with `VITE_INCLUDE_GALLERY=1 electron-vite build` (see
// package.json's `pree2e`). Vite inlines both `import.meta.env.*` reads as literals at build time.
const includeGallery = import.meta.env.DEV || import.meta.env.VITE_INCLUDE_GALLERY === "1";

/**
 * The gallery page is the v1 primitive catalogue plus the v2 density block. They are two
 * components rather than one file because the density pass owns its own examples (DESIGN.md §3)
 * and the v1 catalogue stays the reference for everything the pass did not touch.
 *
 * Both are loaded through a *dynamic* `import()`, inside a branch gated by `includeGallery` — not
 * as static top-level imports. A static `import { Gallery } from "../../dev/Gallery"` used to sit
 * at the top of this file; it was captured by the exported `page.Component` regardless of
 * `includeGallery`'s value (the reference lives on the object either way), so Rollup could never
 * prove it unreachable and the claim below was false: lane SCB measured "Design gallery" /
 * "Every primitive" / "Mount scene" all present in a *plain* `npm run build`'s output
 * (`out/renderer/assets/index-*.js`, 1,386,127 bytes). Writing the same `includeGallery` check as
 * the literal condition of a dynamic `import()` lets esbuild's constant folding (it runs on every
 * module's transform, not only under `--minify`) prove the branch dead when both
 * `import.meta.env.*` reads fold to `false`/`undefined`, and remove the branch — dynamic import
 * included — before Rollup ever walks it as an edge in the module graph. Verified: after this
 * change, a plain `npm run build`'s `out/renderer` has zero occurrences of "Design gallery",
 * "Every primitive" or "Mount scene" in any asset (the only survivor of the three strings SCB
 * grepped for is this file's own `purpose` text below, "Every design-system primitive, every
 * state." — page metadata that has to stay, since `registry.ts` eager-imports every page
 * directory's `index.tsx` unconditionally to build the nav and the command palette). The main chunk
 * shrank from 1,386,127 to 1,309,259 bytes and `uplot` (a chart lib the gallery, not the app,
 * demos) from 137.84 kB to 35.88 kB per `electron-vite build`'s own report — both `Gallery.tsx`
 * and `DensityGallery.tsx`'s code dropped out entirely, not just hidden behind `enabled: false`.
 *
 * `App.tsx` renders every `page.Component` with no `<Suspense>` ancestor (only `PageErrorBoundary`,
 * which catches thrown errors, not a suspended lazy import), so the lazy component is wrapped in
 * its own `<Suspense>` right here rather than requiring an App.tsx change this lane does not own.
 */
const LazyDesignGallery: ComponentType | null = includeGallery
  ? lazy(async () => {
      const [{ Gallery }, { DensityGallery }] = await Promise.all([
        import("../../dev/Gallery"),
        import("./DensityGallery"),
      ]);
      return {
        default: function DesignGalleryImpl() {
          return (
            <>
              <Gallery />
              <DensityGallery />
            </>
          );
        },
      };
    })
  : null;

function DesignGalleryPage() {
  if (!LazyDesignGallery) return null;
  return (
    <Suspense fallback={null}>
      <LazyDesignGallery />
    </Suspense>
  );
}

const page: PageDef = {
  id: "dev",
  title: "Gallery",
  purpose: "Every design-system primitive, every state.",
  navGroup: "dev",
  order: 999,
  icon: FlaskConical,
  Component: DesignGalleryPage,
  enabled: includeGallery,
};

export default page;
