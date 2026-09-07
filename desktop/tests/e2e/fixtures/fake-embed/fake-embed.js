/**
 * Deterministic stand-in for the real Tetravox embed, for the desktop e2e suite (no WebGL2/WASM
 * needed under Electron's offscreen harness). Speaks the small subset of embed protocol 2 that the
 * Viewer page and the run-page scene panes drive: meshes/layers from protocol 1, plus points,
 * pick events and camera replies.
 *
 * Envelope: { tvx: 1, type, id?, ...payload }. `tvx` is still 1 for protocol-2 bundles; the
 * additive feature level lives in `/tetravox/manifest.json.protocol` and `ready.version`.
 */
(function () {
  "use strict";

  var params = new URLSearchParams(window.location.search);
  var hostOrigin = params.get("hostOrigin") || "*";
  var statusEl = document.getElementById("status");
  var layersEl = document.getElementById("layers");
  var pointsEl = document.getElementById("points");

  var DEFAULT_CAMERA = {
    target: [0, 0, 0],
    distance: 300,
    rotation: [0, 0, 0, 1],
    fovYDeg: 35,
    orthographic: false,
    near: 1,
    far: 1200,
  };

  // `lastScene` is the raw EmbedViewSpec from the most recent `load` (kept verbatim, not the
  // reduced `state.layers`/`state.datasets` view), so `serialize` can echo back something shaped
  // like the ViewSpec the protocol promises rather than reply with nothing.
  var state = { layers: [], datasets: [], lastScene: null, pickEvents: false, pointToolLayerId: null, camera: copyCamera(DEFAULT_CAMERA) };

  var hostMessageTypes = [];

  function post(type, payload) {
    var msg = Object.assign({ tvx: 1, type: type }, payload || {});
    window.parent.postMessage(msg, hostOrigin === "*" ? "*" : hostOrigin);
  }

  function copyCamera(camera) {
    return Object.assign({}, camera, { target: (camera.target || [0, 0, 0]).slice(), rotation: (camera.rotation || [0, 0, 0, 1]).slice() });
  }

  function copyLayer(layer) {
    return Object.assign({}, layer, {
      label: layer.label && typeof layer.label === "object" ? Object.assign({}, layer.label) : layer.label,
      points: Array.isArray(layer.points)
        ? layer.points.map(function (p) {
            return Object.assign({}, p, { position: Array.isArray(p.position) ? p.position.slice() : p.position, color: Array.isArray(p.color) ? p.color.slice() : p.color });
          })
        : layer.points,
    });
  }

  function readyMessage() {
    // A parenthesised ANGLE-shaped string so the host's `shortRenderer` (which pulls the middle
    // field out of the wrapper) has something real to parse — the `status-renderer` cell's own
    // e2e coverage (viewer.spec.ts).
    return {
      version: 2,
      caps: { webgl2: true, renderer: "ANGLE (Fake, Fake GPU, OpenGL 4.1)", features: ["meshes", "scalars", "labels", "markers", "pick", "camera"] },
    };
  }

  /** `[r,g,b,a]` in 0..1 -> the `rgb(r,g,b)` a spec can compare against `channelCss`. */
  function cssColor(rgba) {
    if (!Array.isArray(rgba) || rgba.length < 3) return "";
    return "rgb(" + rgba.slice(0, 3).map(function (c) { return Math.round(c * 255); }).join(",") + ")";
  }

  /**
   * Mirror the first points layer into the DOM.
   *
   * This is the fixture's whole contribution to the electrode tests: the state and colour of every
   * point are what the host *sent*, echoed where a spec can read them, and a click on a row is a
   * pick of THAT point. Nothing here interprets the colours — the fake has no renderer and must
   * not pretend to have one.
   */
  function renderPoints() {
    if (!pointsEl) return;
    var layer = firstPointLayer();
    var points = layer && Array.isArray(layer.points) ? layer.points : [];
    pointsEl.innerHTML = "";
    points.forEach(function (point) {
      var li = document.createElement("li");
      li.dataset.pointId = point.id || "";
      li.dataset.state = point.state || "";
      li.dataset.color = cssColor(point.color);
      li.dataset.name = point.name === undefined ? "" : String(point.name);
      li.dataset.radiusPx = point.radiusPx === undefined ? "" : String(point.radiusPx);
      li.textContent = (point.id || "?") + " " + (point.state || "");
      pointsEl.appendChild(li);
    });
  }

  function renderLayers() {
    layersEl.innerHTML = "";
    state.layers.forEach(function (layer) {
      var li = document.createElement("li");
      li.dataset.layerId = layer.id;
      li.dataset.kind = layer.kind || "";
      li.dataset.visible = String(layer.visible !== false);
      li.dataset.opacity = String(layer.opacity);
      li.dataset.points = String(Array.isArray(layer.points) ? layer.points.length : 0);
      li.textContent = (layer.name || layer.id) + (layer.visible === false ? " (hidden)" : "");
      layersEl.appendChild(li);
    });
  }

  function setStatus(phase) {
    statusEl.textContent = phase;
  }

  function normaliseLayer(layer) {
    return Object.assign(
      {
        id: layer.id,
        name: layer.name || layer.id,
        kind: layer.kind || "volume",
        visible: layer.visible !== false,
        opacity: layer.opacity === undefined ? 1 : layer.opacity,
      },
      layer,
      { points: Array.isArray(layer.points) ? layer.points.slice() : layer.points },
    );
  }

  function liveLayers() {
    return state.layers.map(copyLayer);
  }

  function emitLayers() {
    renderLayers();
    renderPoints();
    post("layers", { layers: liveLayers() });
  }

  function handleLoad(payload) {
    var scene = (payload && payload.scene) || {};
    state.lastScene = scene;
    state.datasets = Array.isArray(scene.datasets) ? scene.datasets : [];
    state.layers = Array.isArray(scene.layers)
      ? scene.layers.map(function (l) {
          return normaliseLayer(l || {});
        })
      : [];
    if (scene.view3d && scene.view3d.camera) state.camera = copyCamera(scene.view3d.camera);
    renderLayers();
    renderPoints();
    setStatus("ready");
    post("loaded", {
      id: payload && payload.id,
      // Objects, not bare id strings, so the host's dataset mirror (and the inspector's size badge)
      // exercises the shape the real embed sends. Sizes are derived from the index, deterministic.
      datasets: state.datasets.map(function (d, i) {
        return { id: d.id, name: d.name, kind: d.kind === "mesh" ? "mesh" : "volume", bytes: (i + 1) * 1024 * 1024 };
      }),
      layers: liveLayers(),
    });
    post("status", { phase: "ready" });
  }

  function handleSetCursor(payload) {
    post("cursor", { world: payload && payload.world });
  }

  function labelValueForLayer(layer) {
    if (!layer || !layer.label) return null;
    if (Array.isArray(layer.label.visibleLabels) && layer.label.visibleLabels.length > 0) return Number(layer.label.visibleLabels[0]);
    return 1;
  }

  function handleProbe(payload) {
    var world = (payload && payload.world) || [0, 0, 0];
    post("probe", {
      id: payload && payload.id,
      result: {
        world: world,
        rows: state.layers.map(function (l) {
          var labelId = labelValueForLayer(l);
          return labelId === null
            ? { layerId: l.id, layerName: l.name, kind: l.kind, value: null }
            : { layerId: l.id, layerName: l.name, kind: l.kind, value: labelId, labelId: labelId, labelName: "fake region" };
        }),
      },
    });
  }

  // 1x1 transparent PNG -- deterministic, no canvas/WebGL needed.
  var ONE_PX_PNG =
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

  function handleScreenshot(payload) {
    post("screenshot", { id: payload && payload.id, dataUrl: ONE_PX_PNG });
  }

  function findLayer(id) {
    for (var i = 0; i < state.layers.length; i++) {
      if (state.layers[i].id === id) return state.layers[i];
    }
    return null;
  }

  function handleSetLayerVisible(payload) {
    var layer = findLayer(payload && payload.layerId);
    if (layer) layer.visible = !!(payload && payload.visible);
    emitLayers();
  }

  function handleSetLayerOpacity(payload) {
    var layer = findLayer(payload && payload.layerId);
    if (layer) layer.opacity = payload && payload.opacity;
    emitLayers();
  }

  function handleUpdateLayer(payload) {
    var layer = findLayer(payload && payload.layerId);
    if (layer && payload && payload.patch && typeof payload.patch === "object") Object.assign(layer, payload.patch);
    emitLayers();
  }

  function handleSetPoints(payload) {
    var layer = findLayer(payload && payload.layerId);
    if (layer) layer.points = payload && Array.isArray(payload.points) ? payload.points.slice() : [];
    emitLayers();
  }

  function handleSetPointSelection(payload) {
    var layer = findLayer(payload && payload.layerId);
    var selected = payload && payload.pointId;
    if (layer && Array.isArray(layer.points)) {
      layer.points = layer.points.map(function (point) {
        return Object.assign({}, point, { state: point.id && point.id === selected ? "selected" : "idle" });
      });
    }
    emitLayers();
  }

  function handleSetCamera(payload) {
    if (payload && payload.patch && typeof payload.patch === "object") state.camera = copyCamera(Object.assign({}, state.camera, payload.patch));
    post("camera", { id: payload && payload.id, camera: copyCamera(state.camera) });
  }

  function handleGetCamera(payload) {
    post("camera", { id: payload && payload.id, camera: copyCamera(state.camera) });
  }

  /** Reply to `serialize`: the last loaded scene, verbatim (or an empty ViewSpec shape before any
   * `load` has happened). This is `Engine.serialize()`'s job upstream; the fake just remembers
   * what it was told rather than re-deriving anything from `state.layers`. */
  function handleSerialize(payload) {
    var spec = state.lastScene || { datasets: [], layers: [] };
    post("scene", { id: payload && payload.id, spec: spec });
  }

  function handleReset() {
    state = { layers: [], datasets: [], lastScene: null, pickEvents: false, pointToolLayerId: null, camera: copyCamera(DEFAULT_CAMERA) };
    renderLayers();
    setStatus("idle");
    post("status", { phase: "idle" });
    post("layers", { layers: [] });
  }

  function firstPointLayer() {
    for (var i = 0; i < state.layers.length; i++) {
      if (state.layers[i].kind === "points" || Array.isArray(state.layers[i].points)) return state.layers[i];
    }
    return null;
  }

  function firstLabelLayer() {
    for (var i = 0; i < state.layers.length; i++) {
      if (state.layers[i].label) return state.layers[i];
    }
    return null;
  }

  function postPick() {
    var world = [12, -18, 9];
    var points = firstPointLayer();
    if (points) {
      var point = Array.isArray(points.points) && points.points.length > 0 ? points.points[0] : { id: "E1", position: world };
      post("pick", {
        kind: "point",
        world: point.position || world,
        layerId: points.id,
        pointId: point.id || "E1",
        modifiers: { shift: false, ctrl: false, alt: false, meta: false },
        probe: { world: point.position || world, rows: [] },
      });
      return;
    }
    var labels = firstLabelLayer();
    var labelId = labelValueForLayer(labels) || 1;
    post("pick", {
      kind: labels ? "tri" : "cursor",
      world: world,
      layerId: labels && labels.id,
      label: labels ? { id: labelId, name: "fake region", layerId: labels.id } : undefined,
      modifiers: { shift: false, ctrl: false, alt: false, meta: false },
      probe: {
        world: world,
        rows: labels ? [{ layerId: labels.id, layerName: labels.name, kind: labels.kind, value: labelId, labelId: labelId, labelName: "fake region" }] : [],
      },
    });
  }

  function onMessage(event) {
    if (event.source !== window.parent) return;
    if (hostOrigin !== "*" && event.origin !== hostOrigin) return;
    var msg = event.data;
    if (!msg || msg.tvx !== 1 || typeof msg.type !== "string") return;

    // Every host message type this fake has ever received, in order, deduplicated into a list a
    // spec can read. The electrode work is gated on messages the pane must NEVER send
    // (`setPointTool`, `setPointSelection` — the selection RING), and "never" is only checkable
    // against a record of what did arrive.
    hostMessageTypes.push(msg.type);
    document.body.dataset.hostMessages = hostMessageTypes.join(",");

    switch (msg.type) {
      case "hello":
        post("ready", readyMessage());
        break;
      case "load":
        handleLoad(msg);
        break;
      case "setCursor":
        handleSetCursor(msg);
        break;
      case "probe":
        handleProbe(msg);
        break;
      case "screenshot":
        handleScreenshot(msg);
        break;
      case "setLayerVisible":
        handleSetLayerVisible(msg);
        break;
      case "setLayerOpacity":
        handleSetLayerOpacity(msg);
        break;
      case "updateLayer":
        handleUpdateLayer(msg);
        break;
      case "setPoints":
        handleSetPoints(msg);
        break;
      case "setPointSelection":
        handleSetPointSelection(msg);
        break;
      case "setPointTool":
        state.pointToolLayerId = msg.layerId || null;
        post("pointTool", { event: { layerId: state.pointToolLayerId, mode: msg.mode || "select" } });
        break;
      case "setPickEvents":
        state.pickEvents = !!msg.enabled;
        break;
      case "getCamera":
        handleGetCamera(msg);
        break;
      case "setCamera":
        handleSetCamera(msg);
        break;
      case "serialize":
        handleSerialize(msg);
        break;
      case "reset":
        handleReset();
        break;
      case "setTheme":
        // Recorded, not rendered: the assertion the desktop suite needs is "the host actually sent
        // the app's resolved theme", and a data attribute is the cheapest honest witness of that.
        // The real embed repaints its own chrome here.
        document.body.setAttribute("data-theme", String(msg.theme));
        break;
      case "setLayout":
      case "setActiveLayer":
      case "focus":
        // Accepted, deterministically inert (no visual state this fake tracks) -- present so a
        // host that sends them mid-suite never sees an "unknown message" failure.
        break;
      default:
        break;
    }
  }

  window.addEventListener("message", onMessage);
  post("ready", readyMessage());

  // v3 (program U5) deleted the host's own Cursor inspector block: the RAS status-bar cell is now
  // fed only by the embed's OWN cursor events, exactly as a real crosshair drag would. A click
  // anywhere on this fake stands in for that — deterministic, so the e2e assertion is exact.
  document.body.addEventListener("click", function (event) {
    var pointRow = event.target && event.target.closest("#points li");
    if (pointRow) {
      var layer = firstPointLayer();
      var id = pointRow.dataset.pointId;
      var hit = null;
      if (layer && Array.isArray(layer.points)) {
        for (var i = 0; i < layer.points.length; i++) {
          if (layer.points[i].id === id) hit = layer.points[i];
        }
      }
      if (hit) {
        post("pick", {
          kind: "point",
          world: hit.position,
          layerId: layer.id,
          pointId: hit.id,
          modifiers: { shift: false, ctrl: false, alt: false, meta: false },
          probe: { world: hit.position, rows: [] },
        });
      }
      return;
    }
    if (event.target && event.target.closest("li")) return; // a layer row click is not a pick
    post("cursor", { world: [12, -18, 9], space: "subject" });
    postPick();
  });
})();
