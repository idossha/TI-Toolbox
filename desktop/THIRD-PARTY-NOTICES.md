# Third-party notices

TI-Toolbox desktop is licensed under the GPL-3.0 (`desktop/package.json`). It redistributes the
components below, whose licences are permissive and whose notices must travel with the built
application and with the bundle `tit.server` serves. Nothing here imposes an obligation on
TI-Toolbox's own source.

**This file covers what the *desktop bundle* ships.** Everything the container image ships is the
image's own notice obligation, not this file's — see below for the one component that moved.

---

## Tetravox — no longer bundled here

The 3D viewer is Tetravox, and as of v3 **no Tetravox source, engine or WebAssembly binary is
distributed by this package** (decision D3, `docs/dev/DECISIONS.md § 2026-09-02 (UX redesign)`; D1/D3,
`docs/dev/DECISIONS.md § 2026-09-03 (Docker streamline)`). The earlier cut vendored `@tetravox/{engine,wasm,protocol}`
as source under `desktop/vendor/tetravox/`; that directory, the `file:` dependencies on it, its
`gl-matrix` transitive dependency and the `vendor-tetravox.sh` script are all removed.

What replaced it: Tetravox ships a **released embed bundle** (`tetravox-embed-<ver>.tgz`, MIT),
which is installed into the `idossha/ti-toolbox` container image at build time under
`/opt/tetravox/embed` and served by `tit.server` at `/tetravox/`. The desktop renderer mounts it in
an `<iframe>` and drives it over `postMessage`. So the licence notice for Tetravox and for its
`gl-matrix` dependency travels with **the image**, alongside the bundle's own `LICENSE` file (the
tarball ships one, per the tetravox repo's `docs/EMBED.md` §1) — not with this package.

The only Tetravox-derived text in this repository is
`desktop/src/renderer/viewer/protocol.ts`: a copy of the embed's published protocol *type
declarations* (message interfaces and guards, MIT, upstream commit named in that file's header).
It contains no engine, renderer or WASM code, and it exists so the host can type-check its half of
the contract without depending on the package.

Homepage: https://github.com/idossha/tetravox

```
MIT License

Copyright (c) 2026 Ido Haber

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
