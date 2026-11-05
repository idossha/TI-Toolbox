"""A single-file interactive viewer of a tractogram coloured by the TI field along each fibre.

:func:`write_viewer` writes one self-contained HTML page: the data are embedded (base64 typed
arrays in a JSON block) and three.js comes from jsDelivr at a pinned version, so the file opens
from disk or a mail attachment. The page offers per-vertex colouring by ``ti_along``,
``ti_max``, ``ti_along / ti_max`` or direction, a ``ti_along`` threshold, an edge filter, a
decimated glass brain, the montage's electrodes and orbit controls; it follows the system
light/dark preference and fits a phone.

Coordinates are subject world RAS mm (the SimNIBS mesh frame), stored as int16 hundredths of
a millimetre about the brain centre; field values as uint16 fractions of each metric's maximum.
"""

from __future__ import annotations

import base64
import html
import json

import numpy as np

from tit.blender import tract_data as td

THREE_VERSION = "0.160.0"
#: Budget the payload is cut to fit; the page stays well under 12 MB.
WEB_STREAMLINES = 6000
WEB_STEP_MM = 2.0
WEB_TRIANGLES = 40_000
POSITION_SCALE = 100.0  # int16 units per mm: 0.01 mm steps, +-327 mm range


def _b64(array: np.ndarray, dtype: str) -> str:
    return base64.b64encode(np.ascontiguousarray(array, dtype=dtype).tobytes()).decode()


def _quantize(points: np.ndarray, centre: np.ndarray) -> np.ndarray:
    q = np.rint((np.asarray(points, dtype=np.float64) - centre) * POSITION_SCALE)
    if np.abs(q).max(initial=0) > 32767:
        raise ValueError("coordinates span more than +-327 mm about the brain centre")
    return q.astype("<i2")


def viewer_payload(
    tracts: td.Tracts,
    glass: tuple[np.ndarray, np.ndarray],
    electrodes: list[dict],
    edges: dict[int, dict],
    *,
    title: str,
    max_streamlines: int = WEB_STREAMLINES,
    seed: int = 0,
    n_total: int | None = None,
) -> dict:
    """The JSON the page reads; every array a base64 little-endian typed array.

    *n_total* is the size of the tractogram *tracts* was drawn from, when it is a subset.
    """
    weight = tracts.dps.get("ti_along_max")
    if weight is None:
        weight = np.maximum.reduceat(tracts.dpv["ti_along"], tracts.offsets[:-1])
    keep = td.subsample(weight, max_streamlines, seed)
    picked = td.select(tracts, keep)
    # The threshold reads the raw per-streamline peak; colours are display-smoothed.
    along_max = np.asarray(
        picked.dps.get(
            "ti_along_max",
            np.maximum.reduceat(picked.dpv["ti_along"], picked.offsets[:-1]),
        ),
        dtype=np.float32,
    )
    channels = [k for k in ("ti_along", "ti_max", "ti_avg") if k in picked.dpv]
    for key in channels:
        picked.dpv[key] = td.smooth_along(picked, picked.dpv[key])
    t = td.decimate(picked, WEB_STEP_MM)
    edge_id = t.dps.get("edge_id", np.full(t.n, -1)).astype(np.int64)

    from tit.scene.simplify import simplify_to_budget

    surface = simplify_to_budget(glass[0], glass[1], WEB_TRIANGLES)
    centre = (surface.vertices.max(0) + surface.vertices.min(0)) / 2.0
    scales = {}
    for key in channels:
        scales[key] = float(max(t.dpv[key].max(initial=0.0), 1e-12))
    metric_max = {
        "ti_along": td.robust_max(t.dpv["ti_along"]),
        "ti_max": td.robust_max(t.dpv["ti_max"]),
        "ti_ratio": 1.0,
        "align_index": 2.0**td.ALIGN_OCTAVES,
    }

    # Strongest edges first, unassigned last: by the edge's median streamline ti_along_mean
    # from edges.json (a whole-edge statistic), else by the shown fibres' median peak.
    def strength(e: int) -> float:
        median = (edges.get(e, {}).get("ti_along_mean") or {}).get("median")
        return (
            float(median)
            if median is not None
            else float(np.median(along_max[edge_id == e]))
        )

    listed = sorted({int(e) for e in edge_id}, key=lambda e: (e < 0, -strength(e)))
    return {
        "title": title,
        "three": THREE_VERSION,
        "centre": [float(c) for c in centre],
        "scale": POSITION_SCALE,
        "stops": td.PLASMA_SRGB,
        "stops_diverging": td.COOLWARM_SRGB,
        "align_octaves": td.ALIGN_OCTAVES,
        "metrics": {k: {"label": v[0], "units": v[1]} for k, v in td.METRICS.items()},
        "metric_max": metric_max,
        "n_streamlines": int(t.n),
        "n_total": int(n_total or tracts.n),
        "positions": _b64(_quantize(t.points, centre), "<i2"),
        "offsets": _b64(t.offsets, "<u4"),
        "values": {
            k: _b64(np.rint(t.dpv[k] / s * 65535), "<u2") for k, s in scales.items()
        },
        "value_scale": scales,
        "along_max": _b64(along_max, "<f4"),
        "edge_id": _b64(edge_id, "<i4"),
        "edges": [
            {
                "id": e,
                "name": (
                    td.edge_name(edges[e])
                    if e in edges
                    else ("unassigned" if e < 0 else f"edge {e}")
                ),
                "n": int(edges.get(e, {}).get("n_streamlines", (edge_id == e).sum())),
            }
            for e in listed
        ],
        "glass": {
            "positions": _b64(_quantize(surface.vertices, centre), "<i2"),
            "triangles": _b64(surface.triangles, "<u4"),
        },
        "electrodes": [
            {
                "name": e["name"],
                "xyz": [float(c - m) for c, m in zip(e["xyz"], centre)],
                "channel": int(e["channel"]),
            }
            for e in electrodes
        ],
    }


def write_viewer(
    path: str,
    tracts: td.Tracts,
    glass: tuple[np.ndarray, np.ndarray],
    electrodes: list[dict],
    edges: dict[int, dict],
    *,
    title: str,
    n_total: int | None = None,
) -> str:
    """Write the viewer page to *path* and return it."""
    payload = viewer_payload(
        tracts, glass, electrodes, edges, title=title, n_total=n_total
    )
    page = (
        _PAGE.replace("__TITLE__", html.escape(title))
        .replace("__THREE__", THREE_VERSION)
        .replace(
            "__DATA__", json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
        )
    )
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(page)
    return path


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tract Field Viewer</title>
<style>
:root {
  --bg: #f6f7f9; --panel: #ffffff; --ink: #1b1f24; --muted: #5d6670; --line: #d9dde3;
  --accent: #2f6fdb; --glass: #46556a; --scene: #f6f7f9;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0b0d10; --panel: #14171c; --ink: #e8ebef; --muted: #9aa3ad; --line: #2a2f37;
    --accent: #7aa7ff; --glass: #9fb4d6; --scene: #050608;
  }
}
:root[data-theme="dark"] {
  --bg: #0b0d10; --panel: #14171c; --ink: #e8ebef; --muted: #9aa3ad; --line: #2a2f37;
  --accent: #7aa7ff; --glass: #9fb4d6; --scene: #050608;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--ink); font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { display: grid; grid-template-columns: minmax(0, 1fr) 320px; height: 100vh; }
#view { position: relative; min-height: 0; background: var(--scene); }
#view canvas { display: block; width: 100%; height: 100%; touch-action: none; }
#bar { position: absolute; left: 16px; bottom: 16px; width: min(280px, calc(100% - 32px)); font-size: 12px; color: var(--ink);
  background: color-mix(in srgb, var(--panel) 80%, transparent); padding: 8px 10px; border-radius: 6px; }
#ramp { height: 10px; border-radius: 2px; margin: 4px 0 2px; }
#bar .ends { display: flex; justify-content: space-between; color: var(--muted); }
aside { background: var(--panel); border-left: 1px solid var(--line); padding: 16px; overflow-y: auto; }
h1 { font-size: 15px; margin: 0 0 4px; }
.note { color: var(--muted); font-size: 12px; margin: 0 0 12px; }
label.field { display: block; margin: 12px 0 4px; font-weight: 600; font-size: 13px; }
select, input[type=range] { width: 100%; }
select { padding: 6px; background: var(--bg); color: var(--ink); border: 1px solid var(--line); border-radius: 4px; }
.row { display: flex; gap: 8px; align-items: center; justify-content: space-between; }
.toggles label { display: inline-flex; gap: 6px; align-items: center; margin-right: 12px; font-size: 13px; }
button { background: none; border: 1px solid var(--line); color: var(--ink); border-radius: 4px; padding: 3px 10px; cursor: pointer; font: inherit; }
button:hover { border-color: var(--accent); }
#edges { list-style: none; margin: 6px 0 0; padding: 0; max-height: 40vh; overflow-y: auto; border-top: 1px solid var(--line); }
#edges li { border-bottom: 1px solid var(--line); }
#edges label { display: flex; gap: 8px; align-items: center; padding: 5px 2px; font-size: 13px; cursor: pointer; }
#edges .n { margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }
output { font-variant-numeric: tabular-nums; color: var(--muted); }
@media (max-width: 720px) {
  main { grid-template-columns: 1fr; grid-template-rows: 62vh auto; height: auto; }
  aside { border-left: 0; border-top: 1px solid var(--line); }
  #edges { max-height: 45vh; }
}
</style>
<script type="importmap">
{"imports": {"three": "https://cdn.jsdelivr.net/npm/three@__THREE__/build/three.module.js",
             "three/addons/": "https://cdn.jsdelivr.net/npm/three@__THREE__/examples/jsm/"}}
</script>
</head>
<body>
<main>
  <div id="view"><div id="bar"><div id="barlabel"></div><div id="ramp"></div><div class="ends"><span id="lo"></span><span id="hi"></span></div></div></div>
  <aside>
    <h1>__TITLE__</h1>
    <p class="note" id="count"></p>
    <label class="field" for="metric">Colour by</label>
    <select id="metric">
      <option value="ti_along">TI envelope along the fibre (V/m)</option>
      <option value="ti_max">TI_max at the fibre (V/m)</option>
      <option value="ti_ratio">ti_along / ti_max</option>
      <option value="align_index">Field along fibre ÷ random-direction baseline</option>
      <option value="direction">Fibre direction (RGB)</option>
    </select>
    <label class="field" for="threshold">Streamline peak ti_along &ge; <output id="thrval"></output></label>
    <input id="threshold" type="range" min="0" max="1000" value="0">
    <div class="toggles" style="margin-top:12px">
      <label><input type="checkbox" id="showglass" checked> Glass brain</label>
      <label><input type="checkbox" id="showelec" checked> Electrodes</label>
    </div>
    <div class="row" style="margin-top:12px"><label class="field" style="margin:0">Edges</label>
      <span><button id="all" type="button">All</button> <button id="none" type="button">None</button></span></div>
    <ul id="edges"></ul>
    <p class="note" style="margin-top:12px">Field values are descriptors of the applied field along each fibre, not predictions of activation. Colours are averaged along each fibre over &plusmn;3 mm; the threshold uses each streamline's raw peak.</p>
  </aside>
</main>
<script type="application/json" id="data">__DATA__</script>
<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const D = JSON.parse(document.getElementById("data").textContent);
const bytes = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0)).buffer;
const typed = (s, T) => new T(bytes(s));
const s = 1 / D.scale;

const pos = Float32Array.from(typed(D.positions, Int16Array), (q) => q * s);
const offsets = typed(D.offsets, Uint32Array);
const nVert = pos.length / 3, nLine = offsets.length - 1;
const vals = {};
for (const k of Object.keys(D.values)) {
  const q = typed(D.values[k], Uint16Array), scale = D.value_scale[k] / 65535;
  vals[k] = Float32Array.from(q, (x) => x * scale);
}
vals.ti_ratio = vals.ti_along.map((a, i) => (vals.ti_max[i] > 0 ? a / vals.ti_max[i] : 0));
if (vals.ti_avg) vals.align_index = vals.ti_along.map((a, i) => (vals.ti_avg[i] > 0 ? a / vals.ti_avg[i] : 1));
else document.querySelector('#metric option[value="align_index"]').remove();
const alongMax = typed(D.along_max, Float32Array);
const edgeId = typed(D.edge_id, Int32Array);
const lineOf = new Uint32Array(nVert);
for (let l = 0; l < nLine; l++) lineOf.fill(l, offsets[l], offsets[l + 1]);

const tangent = new Float32Array(nVert * 3);
for (let l = 0; l < nLine; l++) {
  for (let i = offsets[l]; i < offsets[l + 1]; i++) {
    const a = Math.max(i - 1, offsets[l]), b = Math.min(i + 1, offsets[l + 1] - 1);
    const dx = pos[3*b] - pos[3*a], dy = pos[3*b+1] - pos[3*a+1], dz = pos[3*b+2] - pos[3*a+2];
    const n = Math.hypot(dx, dy, dz) || 1;
    tangent[3*i] = Math.abs(dx / n); tangent[3*i+1] = Math.abs(dy / n); tangent[3*i+2] = Math.abs(dz / n);
  }
}
function cmap(v, out, o, stops) {
  const x = Math.min(Math.max(v, 0), 1) * (stops.length - 1), i = Math.min(Math.floor(x), stops.length - 2), f = x - i;
  for (let c = 0; c < 3; c++) out[o + c] = stops[i][c] * (1 - f) + stops[i + 1][c] * f;
}
const diverging = (m) => m === "align_index";
// A colour-map position: linear to the metric's top, or log2 about 1 for a diverging ratio.
const position = (m, value) => diverging(m)
  ? 0.5 + 0.5 * Math.log2(Math.max(value, 1e-6)) / D.align_octaves
  : value / D.metric_max[m];

const view = document.getElementById("view");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
view.prepend(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
const controls = new OrbitControls(camera, renderer.domElement);
camera.up.set(0, 0, 1);

const geom = new THREE.BufferGeometry();
geom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
const colours = new Float32Array(nVert * 3);
geom.setAttribute("color", new THREE.BufferAttribute(colours, 3));
const lines = new THREE.LineSegments(geom, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true }));
scene.add(lines);

const gpos = Float32Array.from(typed(D.glass.positions, Int16Array), (q) => q * s);
const gg = new THREE.BufferGeometry();
gg.setAttribute("position", new THREE.BufferAttribute(gpos, 3));
gg.setIndex(new THREE.BufferAttribute(typed(D.glass.triangles, Uint32Array), 1));
gg.computeVertexNormals();
const glassMat = new THREE.ShaderMaterial({
  uniforms: { tint: { value: new THREE.Color() }, strength: { value: 0.45 } },
  transparent: true, depthWrite: false, side: THREE.DoubleSide,
  vertexShader: "varying float f; void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vec3 n = normalize(normalMatrix*normal); f = 1.0 - abs(dot(n, normalize(-mv.xyz))); gl_Position = projectionMatrix*mv; }",
  fragmentShader: "uniform vec3 tint; uniform float strength; varying float f; void main(){ gl_FragColor = vec4(tint, pow(f, 2.5) * strength); }",
});
const glass = new THREE.Mesh(gg, glassMat);
glass.renderOrder = -1; // drawn first, so it tints the background and never veils the fibres
scene.add(glass);

const chan = [0x40bfff, 0x59f273, 0xff8c33, 0xd966ff];
const elec = new THREE.Group();
for (const e of D.electrodes) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(3.5, 20, 12), new THREE.MeshBasicMaterial({ color: chan[e.channel % 4] }));
  m.position.set(...e.xyz); elec.add(m);
}
scene.add(elec);

const box = new THREE.Box3().setFromBufferAttribute(gg.getAttribute("position"));
const radius = box.getSize(new THREE.Vector3()).length() / 2;
let hot = 0; for (let i = 0; i < nVert; i++) if (vals.ti_along[i] > vals.ti_along[hot]) hot = i;
const side = pos[3 * hot] < 0 ? -1 : 1;
const viewDir = new THREE.Vector3(side, 0.35, 0.38).normalize();
function frame() { // fit the bounding sphere in the narrower of the two field-of-view angles
  const half = THREE.MathUtils.degToRad(camera.fov / 2), fit = Math.min(Math.tan(half), Math.tan(half) * camera.aspect);
  camera.position.copy(viewDir).multiplyScalar((radius * 0.95) / fit);
  controls.target.set(0, 0, 0); controls.update();
}

const ui = (id) => document.getElementById(id);
const thrMax = Math.max(...alongMax, 1e-9);
const enabled = new Set(D.edges.map((e) => e.id));
const list = ui("edges");
for (const e of D.edges) {
  const li = document.createElement("li");
  li.innerHTML = `<label title="streamlines in the tractogram"><input type="checkbox" checked data-id="${e.id}"><span></span><span class="n">${e.n}</span></label>`;
  li.querySelector("span").textContent = e.name;
  list.append(li);
}
list.addEventListener("change", (ev) => { const id = +ev.target.dataset.id; ev.target.checked ? enabled.add(id) : enabled.delete(id); rebuild(); });
const setAll = (on) => { for (const box of list.querySelectorAll("input")) { box.checked = on; } D.edges.forEach((e) => (on ? enabled.add(e.id) : enabled.delete(e.id))); rebuild(); };
ui("all").onclick = () => setAll(true);
ui("none").onclick = () => setAll(false);

function recolour() {
  const m = ui("metric").value;
  if (m === "direction") colours.set(tangent);
  else {
    // Low-field fibres fade toward the background, as in the renders, so the hot network reads;
    // a diverging ratio is not faded (its colour is the value, both ends matter).
    const v = vals[m], bg = scene.background, floor = diverging(m) ? 1 : dark.matches ? 0.18 : 0.4;
    const stops = diverging(m) ? D.stops_diverging : D.stops;
    for (let i = 0; i < nVert; i++) {
      const x = Math.min(Math.max(position(m, v[i]), 0), 1), b = floor + (1 - floor) * Math.pow(x, 1.4), o = 3 * i;
      cmap(x, colours, o, stops);
      colours[o] = bg.r + (colours[o] - bg.r) * b; colours[o+1] = bg.g + (colours[o+1] - bg.g) * b; colours[o+2] = bg.b + (colours[o+2] - bg.b) * b;
    }
  }
  geom.getAttribute("color").needsUpdate = true;
  const meta = D.metrics[m];
  ui("barlabel").textContent = meta.label + (meta.units && meta.units !== "1" ? ` (${meta.units})` : "");
  if (m === "direction") { ui("ramp").style.background = "linear-gradient(90deg,#f00,#0f0,#00f)"; ui("lo").textContent = "|x| R  |y| G  |z| B"; ui("hi").textContent = ""; }
  else {
    const stops = diverging(m) ? D.stops_diverging : D.stops;
    ui("ramp").style.background = `linear-gradient(90deg, ${stops.map((c, i) => `rgb(${c.map((x) => Math.round(255 * x)).join(",")}) ${(100 * i) / (stops.length - 1)}%`).join(",")})`;
    if (diverging(m)) { ui("lo").textContent = "0.5 · across"; ui("hi").textContent = "along · 2"; }
    else { ui("lo").textContent = "0"; ui("hi").textContent = D.metric_max[m].toPrecision(2) + (meta.units === "1" ? "" : " " + meta.units); }
  }
  draw();
}
function rebuild() {
  const thr = (ui("threshold").value / 1000) * thrMax;
  ui("thrval").textContent = thr.toFixed(3) + " V/m";
  const idx = []; let shown = 0;
  for (let l = 0; l < nLine; l++) {
    if (alongMax[l] < thr || !enabled.has(edgeId[l])) continue;
    shown++;
    for (let i = offsets[l]; i < offsets[l + 1] - 1; i++) idx.push(i, i + 1);
  }
  geom.setIndex(idx);
  ui("count").textContent = `${shown.toLocaleString()} of ${nLine.toLocaleString()} streamlines shown` + (D.n_total > nLine ? ` (subsampled from ${D.n_total.toLocaleString()})` : "");
  draw();
}
ui("metric").onchange = recolour;
ui("threshold").oninput = rebuild;
ui("showglass").onchange = (e) => { glass.visible = e.target.checked; draw(); };
ui("showelec").onchange = (e) => { elec.visible = e.target.checked; draw(); };

const dark = window.matchMedia("(prefers-color-scheme: dark)");
function theme() {
  const css = getComputedStyle(document.documentElement);
  scene.background = new THREE.Color(css.getPropertyValue("--scene").trim());
  glassMat.uniforms.tint.value.set(css.getPropertyValue("--glass").trim());
  glassMat.uniforms.strength.value = dark.matches ? 0.45 : 0.3;
  draw();
}
dark.addEventListener("change", () => { theme(); recolour(); });

function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); draw();
}
let pending = false;
function draw() { if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; controls.update(); renderer.render(scene, camera); }); } }
controls.addEventListener("change", draw);
new ResizeObserver(resize).observe(view);
if (vals.align_index) ui("metric").value = "align_index"; // reads best when available
theme(); recolour(); rebuild(); resize(); frame(); draw();
window.__tractViewerReady = true;
</script>
</body>
</html>
"""
