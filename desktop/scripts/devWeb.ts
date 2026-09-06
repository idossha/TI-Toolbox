/**
 * `npm run dev:web` — the renderer dev server on its own, with no Electron.
 *
 * NOT `electron-vite dev --rendererOnly`. Measured against electron-vite 5.0.0 on 2026-09-03: that
 * flag only skips *rebuilding* main and preload; `createServer()` calls `startElectron(root)`
 * unconditditionally afterwards (`node_modules/electron-vite/dist/chunks/lib-7y7CgM8M.js`, the
 * `ps = startElectron(inlineConfig.root)` after the `if (options.rendererOnly)` branch). Running it
 * launched a window — the one thing a browser-only dev loop must not do, and on this project also a
 * violation of the "a test run never takes the screen" rule when it happens under an agent.
 *
 * So this does what electron-vite's own `createServer` does for the renderer and stops there: its
 * exported `resolveConfig` resolves `electron.vite.config.ts` exactly as the CLI would — same root,
 * same env dir, same plugins, same proxy — and Vite's own `createServer` serves the result. No
 * second copy of the renderer config exists, so it cannot drift from the Electron path.
 */
import { createServer } from "vite";
import { resolveConfig } from "electron-vite";

export async function runRendererDevServer(root: string): Promise<void> {
  const resolved = await resolveConfig({ root }, "serve", "development");
  const rendererConfig = resolved.config?.renderer;
  if (!rendererConfig) throw new Error(`electron.vite.config.ts under ${root} has no "renderer" config`);
  const server = await createServer(rendererConfig);
  await server.listen();
  server.printUrls();
}
