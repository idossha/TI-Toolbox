import { existsSync } from "node:fs";
import { join } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { createDevProxy } from "./scripts/devProxy";

// In dev the renderer is served by Vite; every renderer request stays origin-relative
// ("/api/...", "/ws/system") and the dev server proxies it to a running tit.server (or the mock).
// `npm run dev` (scripts/dev.ts) sets both of these from the container it just attached to or
// started; the URL default keeps a bare `electron-vite dev` pointing where it always did, and an
// empty token means "inject no Authorization header" — the mock server and a manually connected
// cookie session still work.
const devServer = process.env.TIT_DEV_SERVER_URL ?? "http://127.0.0.1:8765";
const devToken = process.env.TIT_DEV_SERVER_TOKEN ?? "";
const rendererRoot = join(__dirname, "src", "renderer");
/**
 * Serve a request locally when it names a renderer SOURCE file (src/renderer/api/client.ts is
 * requested by Vite as /api/client.ts; src/renderer/ws/useSystemStream.ts as /ws/...), and proxy it
 * to tit.server otherwise. The source directories share their names with the server's route
 * prefixes, and the proxy alone forwarded the module requests to the container (404, blank page).
 */
const serveRendererSource = (req: { url?: string }): string | null =>
  req.url && existsSync(join(rendererRoot, req.url.split("?")[0] ?? "")) ? req.url : null;

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
  },
  preload: {
    // Sandboxed preloads must be CJS and dependency-free; nothing is externalized so the
    // bundle is a single self-contained file.
    build: { rollupOptions: { output: { format: "cjs" } } },
  },
  renderer: {
    // Served by tit.server at "/" (and by the mock server): asset URLs must be relative.
    base: "./",
    plugins: [react(), tailwindcss()],
    // No Tetravox settings here any more (D3, dev/notes/v3-docker-streamline-plan.md): the viewer
    // is a released embed bundle served by tit.server at /tetravox/ and mounted in an <iframe>, so
    // its engine, its module workers and its wasm binary are built and shipped by the tetravox
    // repo and never enter this bundle's module graph. What that removed: an `optimizeDeps.exclude`
    // for the three `@tetravox/*` file: deps, `worker.format: "es"` (nothing here spawns a module
    // worker), and the `assetsInlineLimit: 0` that existed to keep the 848 KB wasm binary a real
    // emitted file.
    server: {
      host: "127.0.0.1",
      // The three entries, the bearer/Origin stamping and why each exists: scripts/devProxy.ts.
      // The bypass stays exactly as it was: the renderer's own source lives under
      // src/renderer/api/ and Vite serves it at /api/... — the same prefix the server API uses.
      // Without it, the module request for /api/client.ts is forwarded to tit.server, answers 404,
      // and the page mounts nothing. Only a path that exists as a renderer source file is served
      // locally; every other /api request (including /api/files/raw/... with any extension) still
      // reaches the server.
      proxy: createDevProxy({ target: devServer, token: devToken, bypass: serveRendererSource }),
    },
    build: {
      rollupOptions: {
        output: {
          // Splits the vendor libraries out of the single ~1.3 MB app chunk so a change to page
          // code doesn't invalidate (and force a re-download of) React/Radix/TanStack/uplot, and
          // so the first paint doesn't wait on parsing everything at once. A function (matching by
          // each module's own path) rather than the object shorthand: the shorthand form pulls in
          // whatever else a listed package reaches eagerly, which produced a real chunk cycle
          // (`react <-> tanstack`, then `radix <-> tanstack`) between these four vendor groups —
          // per-module path matching only ever assigns a module in the direction it is actually
          // imported, so no cycle exists to warn about.
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            if (/[\\/]node_modules[\\/](react|react-dom)[\\/]/.test(id)) return "react";
            if (/[\\/]node_modules[\\/]@radix-ui[\\/]/.test(id)) return "radix";
            if (/[\\/]node_modules[\\/]@tanstack[\\/]/.test(id)) return "tanstack";
            if (/[\\/]node_modules[\\/]uplot[\\/]/.test(id)) return "uplot";
            return undefined;
          },
        },
      },
    },
  },
});
