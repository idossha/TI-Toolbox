# Third-party notices

TI-Toolbox desktop is licensed under the GPL-3.0 (`desktop/package.json`). This file records the
third-party components the desktop bundle carries a notice obligation for, and the ones it used to.
Nothing here imposes an obligation on TI-Toolbox's own source. Everything the container image ships
is the image's own notice obligation, not this file's.

---

## TetraVox — not bundled

The 3D viewer is TetraVox, and **no TetraVox source, engine or WebAssembly binary is distributed
by this package or by the `idossha/ti-toolbox` image** (`docs/dev/DECISIONS.md`
§ 2026-09-13 "Replace browser embedding with managed native TetraVox"). Earlier cuts vendored the
engine under `desktop/vendor/tetravox/` and then served a released embed bundle from the container
at `/tetravox/`; both are gone, along with the embed protocol types the renderer used to carry.

TetraVox is now a separate native application. TI-Toolbox either uses one the user already has or,
from Settings → Viewer, downloads the official release from its own GitHub releases into a per-user
runtime directory after checksum verification. Nothing is redistributed; the notice below is kept
as acknowledgement.

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
