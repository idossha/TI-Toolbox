import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default tseslint.config(
  // release/ and .runtime-staging/ (N0.4 packaging spike, `npm run package`/`package:dir`) are
  // electron-builder's output and its staged Python runtime input, respectively — generated,
  // machine-specific, and (for the runtime) not this project's code at all (pip's own vendored
  // JS inside site-packages was getting linted here otherwise).
  { ignores: ["out/", "dist/", "node_modules/", "playwright-report/", "test-results/", "src/renderer/api/schema.d.ts", "release/", ".runtime-staging/"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/renderer/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: { ...reactHooks.configs.recommended.rules },
  },
  {
    files: ["tests/mock-server/**/*.mjs"],
    languageOptions: { globals: globals.node },
  },
  {
    // The fake Tetravox embed (desktop/tests/e2e/fixtures/fake-embed/fake-embed.js, R2 item 1) is
    // a plain browser script served to Chromium, not bundled through Vite/tsc -- it needs
    // `window`/`document`/`URLSearchParams` as globals the same way the mock server's own .mjs
    // files need Node's.
    files: ["tests/e2e/fixtures/**/*.js"],
    languageOptions: { globals: globals.browser },
  },
);
