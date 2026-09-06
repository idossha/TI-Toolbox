# Skeptic 1 — Release-Engineering Review of R1–R6

Lens: shipping Python inside Electron on macOS/Windows/Linux (packaging, signing, size,
wheels, arm64, Windows process semantics). Every check below is a command I ran or a URL I
fetched myself in this session — not a re-statement of the lane reports. No repo files were
modified.

Verdict key: **UPHELD** (my own check agrees), **REFUTED** (my own check contradicts or the
supporting evidence cited was wrong), **PARTIAL** (conclusion holds, but the cited evidence for
it was itself inaccurate).

---

## 1. Ten load-bearing claims, independently checked

### 1. [R1] SimNIBS is not on PyPI; its hard deps (`cortech`, `brainsynth`, `petsc4py`-fork,
`samseg` wheel) are fetched from GitHub Releases/git, not pip — "add `simnibs` to a bundled
venv's requirements.txt" is false.

**Check:** `curl -s -o /dev/null -w "%{http_code}"` against `pypi.org/pypi/{simnibs,cortech,brainsynth}/json` → **404, 404, 404** (all three). Fetched `environment_macos.yml` from the
v4.6.0 GitHub release directly (`curl -sL .../v4.6.0/environment_macos.yml`) and read it in
full — it contains exactly the six non-PyPI pip entries R1 quotes (`brainnet@git+...`,
`brainsynth@git+...`, and three `https://github.com/{oulap/samseg_wheels,simnibs/cortech,
simnibs/fmm3dpy,simnibs/petsc4py}/releases/download/...` wheel URLs).

**Verdict: UPHELD**, exactly as described, byte-for-byte.

### 2. [R1] Official conda-packed installers: 849,468,729 B (macOS .pkg), 1,268,595,312 B
(Linux .tar.gz), 898,900,463 B (Windows .exe).

**Check:** `curl -s https://api.github.com/repos/simnibs/simnibs/releases/tags/v4.6.0`, parsed
JSON myself. Asset sizes returned: `simnibs_installer_macos.pkg 849468729`,
`simnibs_installer_linux.tar.gz 1268595312`, `simnibs_installer_windows.exe 898900463`.

**Verdict: UPHELD**, exact byte match.

### 3. [R4] macOS x86_64 (Intel) has zero current wheels for `bpy` (≥5.0), `torch==2.6.0`, and
SimNIBS's own `petsc4py` fork — three independent upstreams converging on the same platform
drop.

**Check:** Pulled the full `bpy` release history from `pypi.org/pypi/bpy/json` myself: every
4.5.x release lists `macosx_11_0_x86_64`; **starting at 5.0.0 that platform tag disappears** from
every subsequent release through 5.2.1. Pulled `pypi.org/pypi/torch/2.6.0/json`: 20 wheel
filenames, **zero** contain `x86_64` + `macos`/`macosx` (only `macosx_11_0_arm64` for the Mac
leg, across cp39–cp313). Pulled `api.github.com/repos/simnibs/petsc4py/releases`: all four
releases (v3.21.5–v3.24.2) list only `macosx_14_0_arm64` for macOS, never
`macosx_*_x86_64`.

Independent cross-corroboration found in a source neither R1 nor R4 cited: FastSurfer's own
`INSTALL.md` (fetched directly, §1.6 below) states verbatim *"Intel Macs cannot use the
package: PyTorch has published no macOS x86_64 wheels since 2.2"* — an entirely separate
upstream project citing the identical root cause for the identical platform gap.

**Verdict: UPHELD**, and more strongly corroborated than the lane report itself demonstrated.

### 4. [R4] `python-build-standalone` ships `install_only` CPython 3.11 tarballs for all four
target triples the bundling plan needs (macOS arm64, macOS x64, Windows x64, Linux x64).

**Check:** `curl -s https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest`
→ tag `20260901`. Filtered assets for each of
`{x86_64-unknown-linux-gnu, aarch64-apple-darwin, x86_64-apple-darwin, x86_64-pc-windows-msvc}`
+ `install_only` + `3.11.` — all four present (`cpython-3.11.16+20260901-<triple>-install_only.tar.gz`).

**Verdict: UPHELD.**

### 5. [R2/R3] SimNIBS charm's `subject_atlas`/`atlas2subject` already gives FreeSurfer-free
cortical parcellation (DK40/a2009s/HCP_MMP1) and whole-structure subcortical volumetric labels
with FreeSurfer-identical aseg numeric IDs — i.e. most of "replace recon-all for parcellation"
is already done, zero new code.

**Check (independent re-run, not trusting R2/R3's own transcript):**
```
docker exec tit-v3-spike bash -lc 'which recon-all freeview'   # → empty, both absent
docker exec tit-v3-spike simnibs_python -c "
from simnibs import atlas2subject
labels, ctab, names = atlas2subject('/mnt/000/.../m2m_ernie', 'DK40', split_labels=True,
                                     return_ctab=True, return_names=True)
print(len(names['lh']), list(names['lh'])[:6])"
```
→ `36 ['unknown', 'bankssts', 'caudalanteriorcingulate', 'caudalmiddlefrontal',
'corpuscallosum', 'cuneus']`, 3.55s wall (interpreter startup included), no FreeSurfer binary
on `PATH` anywhere in the container. Also read `labeling_LUT.txt` from the real m2m directory
myself: `10 Left-Thalamus-Proper`, `17 Left-Hippocampus`, `18 Left-Amygdala` — the exact
FreeSurfer aseg numeric-ID scheme.

**Verdict: UPHELD**, reproduced independently end-to-end on the real dataset.

### 6. [R3] FastSurfer `--seg_only` needs no FreeSurfer license/binary, is Apache-2.0, and its
platform matrix is Linux-native + macOS-Apple-Silicon-native + (macOS-Intel/Windows)-Docker-only.

**Check:** Fetched `raw.githubusercontent.com/Deep-MI/FastSurfer/dev/doc/overview/INSTALL.md`
myself and pulled exact quotes: *"An Apple silicon Mac (M1/M2/M3/...) can run the full
pipeline without containerization"* (native); *"Intel Macs cannot use the package: PyTorch has
published no macOS x86_64 wheels since 2.2"* (Docker-only); *"Windows: No native installation
is available ... Docker with WSL2 is required."* Fetched the README separately: segmentation
"does not depend on FreeSurfer binaries, so no license is required for segmentation-only
workflows," full surface pipeline "requires a FreeSurfer license file as it uses some
FreeSurfer binaries internally."

**Verdict: UPHELD**, matches R3's matrix exactly, down to the platform-by-platform reasoning.

### 7. [R5/R6] v3 desktop already fully dropped `dockerode` for CLI-spawn — the "replace
dockerode" third of the maintainer's ask is already done in this branch, not merely proposed.

**Check:** `rg -n "dockerode" desktop/` in the actual worktree → **one hit**, and it's a comment
in `dockerCli.ts` line 2 explaining dockerode is *not* used (*"never dockerode: the only thing
the legacy launcher used the Engine API for was the GUI exec/hijack, which v3 does not
need"*). No `import Docker from "dockerode"` anywhere, no dependency in `desktop/package.json`.

**Verdict: UPHELD.**

### 8. [R5] `dockerode` itself is not stale/abandoned — v5.0.1, published 2026-06-24,
Apache-2.0 — relevant because "build a replacement" is a bigger ask if the library being
replaced is actively maintained and not the problem.

**Check:** `curl -s https://registry.npmjs.org/dockerode` → `dist-tags.latest: "5.0.1"`,
`time["5.0.1"]: "2026-06-24T18:40:08.101Z"`, `license: "Apache-2.0"`. Cross-checked
`raw.githubusercontent.com/apocas/dockerode/master/package.json` independently → same version.

**Verdict: UPHELD.** Worth the maintainer's attention: the case for replacing dockerode is
architectural (CLI-spawn already made it moot; a typed Engine-API client is a further
improvement) — it is not "dockerode is dying," which nothing in the evidence supports.

### 9. [R6] `tit/jobs/runner.py` has a real, currently-unfixed Windows bug: unconditional
`signal.SIGKILL` (line 213) and unconditional `start_new_session=True` (line 86) — both
POSIX-only, so "native on Windows" is not true of this file as it stands today.

**Check:** Read `tit/jobs/runner.py` lines 60-220 directly. Confirmed line 86
`start_new_session=True` with no `os.name`/`sys.platform` branch anywhere in `spawn()`, and
line 213 `proc.send_signal(signal.SIGKILL)` inside `terminate_tree()`, guarded only by
`_ignore_gone()` which (read at line 216-220) catches `psutil.NoSuchProcess`/`AccessDenied` —
**not** `AttributeError`. `python3 -c "import signal; signal.SIGKILL"` on this host succeeds
(POSIX), and `signal.SIGKILL`'s absence on Windows is documented in CPython's own `signal`
module docs (a `SIGKILL`-class constant is listed under "The following constants are specific
to ... POSIX systems"), so this doesn't need a Windows box to confirm — it's a documented
stdlib fact, and the code as read has no guard against it.

**Verdict: UPHELD.** This is a concrete, scoped, unmerged defect (R6 also proposed the fix
shape, borrowed from `tit/pre/utils.py`'s already-correct pattern) — it should be treated as an
open item, not "already handled," when scoping a native-Windows milestone.

### 10. [R1] ADMlib ships inside the general `simnibs` wheel unconditionally, licensed "GPL-v2.0,
non-commercial and academic purposes only" (or a paid Duke commercial license) — a real
commercial-redistribution flag even though TI-Toolbox's own code never calls it.

**Check:** `grep -n -i "admlib\|non-commercial" /Users/idohaber/01_production/simnibs/3RD-PARTY.md`
→ line 4 `ADMlib`, line 8 `GNU General Public Licence (GPL-v2.0), for non-commercial and
academic purposes only`. Read the surrounding block directly (no `pip`-optional-extra guard
mentioned in that file).

**Verdict: UPHELD.** Not independently re-verified whether ADMlib's `.so`/source is physically
present in the *wheel* specifically vs. only the source tree (R1 didn't fully nail this down
either — flagged in "missing" below), but the license text and its unconditional listing in
`3RD-PARTY.md` (which enumerates what SimNIBS *ships*, not what's merely in the git history) is
confirmed as written.

---

## 2. One claim found PARTIAL — a citation error worth flagging to a release engineer

**[R1] "`docker manifest inspect idossha/simnibs:v2.5.0` → single-arch (architecture: amd64,
no `manifests` list)."**

**Check:** I ran `docker manifest inspect idossha/simnibs:v2.5.0` myself. The output **is** a
`schemaVersion: 2` `image.index` with a **`manifests` array containing two entries**: one
`{architecture: amd64, os: linux}` and one `{architecture: unknown, os: unknown}`. The second
entry is almost certainly a buildx attestation/SBOM manifest (a now-common artifact of
`docker buildx build --provenance` / `--sbom`, which registries store as a same-tag manifest
list entry with `unknown/unknown` platform), **not** a second real platform build. So R1's
*conclusion* — no genuine arm64 build exists, this image runs under QEMU emulation on Apple
Silicon — is still correct (independently reconfirmed via `docker image inspect ... --format
'{{.Architecture}} {{.Os}}'` → `amd64 linux`, and `docker exec tit-v3-spike uname -m` → `x86_64`
inside the running container). But the specific evidentiary claim *"no manifests list"* is
factually wrong — there is one, it just doesn't contain an arm64 entry. A release engineer
reading `docker manifest inspect` output for a go/no-go on "does this registry already publish
an arm64 image" needs to know to check each entry's `architecture` field, not just whether a
`manifests` array exists at all — R1's shorthand could mislead someone doing that check quickly
on a different image that *does* have a real second platform manifest sitting next to an
attestation one.

**Verdict: PARTIAL** — conclusion upheld, supporting evidence description inaccurate.

---

## 3. Additional corroboration found beyond what any lane report cited

Checked `api.github.com/repos/oulap/samseg_wheels` (the personal fork R1 flagged as a
supply-chain fragility for the `samseg` wheel every SimNIBS 4.6 install depends on, since it's
neither PyPI nor the `freesurfer/samseg` org). R1 called it a risk but didn't quantify staleness.
I did: `pushed_at: 2024-10-09T15:19:47Z`, exactly **one** release (`dev`), never updated since —
i.e., as of "today" this repo has had no commits or new releases in roughly two years, and the
entire official SimNIBS 4.6.x installer chain (`environment_{linux,macos,windows}.yml`, current
release v4.6.0, published 2026-03-03) still points at that single 2024 release's wheel URLs.
This sharpens R1's flagged risk from "worth noting" to "a single-maintainer, ~2-year-untouched
personal repo is a hard link in SimNIBS's own current official install chain" — a fact any team
vendoring SimNIBS's dependency closure should know before treating that URL as stable
infrastructure. (Also noted in passing: that repo's one release *does* include a
`macosx_13_0_x86_64` wheel for `samseg` specifically — SimNIBS's own `environment_macos.yml`
just doesn't reference it, pinning `macosx_14_0_arm64` only. Doesn't change the Intel-Mac
verdict, since `bpy`/`torch`/`petsc4py`-fork are still blocked regardless.)

---

## 4. What's MISSING — questions a go/no-go decision needs that none of R1–R6 answer

1. **No end-to-end prototype exists anywhere.** All six lanes reason from documentation, PyPI
   metadata, and the container's already-conda-packed env — nobody actually assembled a
   `python-build-standalone` interpreter + pip-installed the SimNIBS wheel + ran `charm` or a
   TI simulation against it, on any platform, in this session. The entire size/wheel/signing
   analysis is sound *paper* engineering; the CGAL-linked `.so` extensions
   (`mesh_tools/cgal/*`), the `mumps` Python bindings SimNIBS imports unconditionally
   (`simnibs/simulation/fem.py` per R4 §9), and whether a curated-wheel install (vs. full
   conda-pack) actually produces a working `charm` run are all still open. This is the single
   highest-value next step before committing engineering time to the plan.
2. **No measured cost for macOS code-signing/notarizing a multi-GB, hundreds-of-Mach-O-file
   tree.** R4 documents the *mechanism* (walk-and-sign script, innermost-first) and flags that
   SimNIBS's own installer explicitly routed around full notarization (the password-zip trick,
   confirmed present in `packing/pack.py`'s own comments) rather than solve this — but nobody
   timed a signing+notarization run against a comparable tree size, so wall-clock CI cost and
   first-attempt failure rate are unknown.
3. **No answer on `mumps` bindings' platform coverage** (imported unconditionally alongside
   `petsc4py` in `simnibs/simulation/fem.py`) — R4 explicitly flags this as unchecked in its own
   §9. Given `petsc4py`'s win-64/macOS-x86_64 story turned out to be the single sharpest
   blocker found in this whole review, `mumps` needs the identical audit before Windows/macOS
   coverage claims are trustworthy end-to-end (not just for the one package that happened to get
   checked).
4. **No decision on whether Intel Mac is actually in scope.** Three independent upstreams
   (`bpy`, `torch`, SimNIBS's `petsc4py` fork) all lack current wheels there — R1/R4 recommend
   dropping it and keeping Docker as the Intel-Mac fallback, but that means the maintainer's
   "no Docker, single native executable" goal is not achievable on Intel Mac without either (a)
   accepting Docker stays required for that one platform, or (b) real engineering to source or
   build older/custom wheels for three separate hard-C/Fortran-heavy packages. Nobody asked the
   maintainer whether Intel Mac is even a supported target for this product.
5. **No resolution of the same tension for Windows/Linux and Docker.** R5/R6 both independently
   conclude QSIPrep/QSIRecon (DWI tractography) stay Docker-only workloads under any realistic
   plan — meaning "completely remove Docker" and "compiled into a desktop electron executable
   like Tetravox or SUNA" are only true for the SimNIBS/TI-simulation core, not for the DWI
   pipeline the toolbox also ships. This is a real scope question for the maintainer to resolve
   (make DWI its own optional/remote feature that still needs Docker, vs. actually eliminating
   it, vs. accepting a permanently-hybrid app) that no lane frames as a decision point — R5
   treats "Docker stays for QSIPrep/QSIRecon" as simply given.
6. **No CPU-only runtime benchmark for FastSurfer `--seg_only`** on the actual target hardware
   class (a user's laptop, not a GPU workstation) — R3 explicitly could not find an official CPU
   number and flags "budget several minutes per subject on CPU until measured" as unresolved.
   This directly affects whether replacing `recon-all` (which users already tolerate as slow) is
   actually good desktop UX or merely a different kind of slow.
7. **No product decision on thalamic-nuclei/hippocampal-subfield segmentation.** R2/R3 agree
   this is the one capability with no FreeSurfer-free replacement found anywhere (not in charm,
   not in FastSurfer). Whether any current or planned TI-Toolbox workflow actually needs
   sub-structure-level targeting is asserted ("TI field foci are typically coarser than
   individual nuclei") but not sourced to an actual user requirement or literature citation —
   this is a domain claim, not a verified fact, and would change the answer if wrong.
8. **No legal read on ADMlib for commercial redistribution.** Confirmed present, confirmed
   "non-commercial only" — but whether it can be excluded from a rebuild via a pip extras
   mechanism, must be stripped post-install, or is a non-issue because the desktop app stays
   GPL-3.0/non-commercial itself, was not run past anyone with actual authority to make that
   call. This is a real risk item for the maintainer specifically (not a code question).
9. **No auto-update / bandwidth-cost analysis** for shipping a 3-4 GB installed app that needs
   periodic updates (a new SimNIBS point release, a `tit` bugfix) — none of R1-R6 touch
   electron-updater delta-patching behavior against a payload this size, which materially
   affects whether "ships like Tetravox/SUNA" (small, frequently-updated apps) is a fair
   comparison at all.
10. **No Linux ARM64 / Windows ARM64 decision.** Confirmed absent from every upstream (SimNIBS
    wheels, `bpy`, `torch`, `petsc4py`-fork) — treated as simply out of scope by R1/R4 without
    the maintainer having said whether that's acceptable.

---

## 5. Bottom line from this pass

Every one of the ten load-bearing claims I selected and independently re-checked **held up**
against my own commands and fetches — a notably clean result for six independent research
passes, and in three cases (FastSurfer's Intel-Mac reasoning matching R4's torch finding
verbatim from a source neither report cross-cited; the exact byte-for-byte installer sizes;
the live `atlas2subject` re-run producing identical output) the cross-corroboration is stronger
than what any single lane demonstrated on its own. The one inaccuracy found (R1's "no manifests
list" description of `docker manifest inspect`) does not change any conclusion — it is a
citation-precision issue, not a substance issue.

That said, "the six reports' claims check out" is a narrower finding than "the maintainer's plan
is de-risked." The research is honest paper-engineering with real primary-source evidence
(PyPI/GitHub JSON, live container runs, direct file reads), but §4 above lists ten questions —
above all, #1 (no actual prototype build exists) and #5 (Docker does not actually go away for
the DWI half of the product) — that no amount of documentation-and-metadata research can answer,
and that a go/no-go decision genuinely needs.
