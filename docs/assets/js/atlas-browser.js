/**
 * Atlas Browser page script (docs/wiki/atlases.md only).
 *
 * Drives the single NiiVue viewer. It draws the selected atlas's template
 * (MNI152 or ernie's T1) as a grayscale base layer and overlays one atlas at
 * a time as a sparse label colormap. Label metadata (id/name/colour/centroid)
 * is read from a JSON blob the page embeds inline (Jekyll does not publish
 * _data/ as a URL, so the data cannot be fetched separately).
 *
 * Expected markup:
 *   <div class="atlas-viewer">
 *     <select class="atlas-select"><option value="mni:cit168">...</select>
 *     <canvas id="atlas-canvas"></canvas>
 *     <p class="atlas-hint"></p>   (the one label: selected atlas + space)
 *   </div>
 *   <div class="atlas-no-webgl" style="display:none">...</div>
 *   <input id=atlas-filter> <span id=atlas-count> <table id=atlas-table>
 *
 * The region table filter copies the case-insensitive substring + <mark> highlight
 * pattern from assets/js/search/results.js verbatim - no new dependency.
 */
(function () {
  'use strict';

  // Derive the site baseurl from this script's own src, so the viewer works
  // both in production (baseurl "/TI-Toolbox") and under serve.sh, which
  // forces --baseurl "". Falls back to the production prefix.
  var BASE = (function () {
    var s = document.querySelector('script[src*="assets/js/atlas-browser.js"]');
    var m = s && s.getAttribute('src').match(/^(.*)\/assets\/js\/atlas-browser\.js/);
    return m ? m[1] : '/TI-Toolbox';
  })();
  var ATLAS_DIR = BASE + '/assets/atlas';
  var ATLAS_OPACITY = 0.7;

  var dataEl = document.getElementById('atlas-data');
  if (!dataEl) {
    return;
  }

  var atlasData = null;
  try {
    atlasData = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }

  /**
   * Detect WebGL2 support the same way NiiVue itself requests a context,
   * without constructing a Niivue instance first.
   */
  function hasWebGL2() {
    try {
      var probe = document.createElement('canvas');
      return !!(window.WebGL2RenderingContext && probe.getContext('webgl2'));
    } catch (e) {
      return false;
    }
  }

  /**
   * Build the {R, G, B, A, I, labels} colormap NiiVue's makeLabelLut() expects.
   *
   * I uses each row's `index` - the compact 1..N value the published display
   * volume was remapped to - NOT its original atlas `id`. NiiVue uploads the
   * LUT as a texture whose width is the highest index, so Destrieux's native
   * 12175 would need a 12176-wide texture against a MAX_TEXTURE_SIZE that is
   * only 8192 on some drivers. It fails silently when it overflows, so the
   * overlay would appear on some GPUs and not others.
   */
  function buildColormapLabel(rows) {
    // Index 0 must be an explicit fully transparent entry. Without it
    // makeLabelLut() gives unlabelled (value 0) voxels an opaque colour and
    // the overlay washes the whole slice in that colour.
    var R = [0];
    var G = [0];
    var B = [0];
    var A = [0];
    var I = [0];
    var labels = ['Background'];
    for (var i = 0; i < rows.length; i++) {
      R.push(rows[i].r);
      G.push(rows[i].g);
      B.push(rows[i].b);
      A.push(255);
      I.push(rows[i].index != null ? rows[i].index : i + 1);
      labels.push(rows[i].name);
    }
    return { R: R, G: G, B: B, A: A, I: I, labels: labels };
  }

  /**
   * One viewer per coordinate space. Instances are fully independent: their
   * own Niivue object, template and currently-loaded overlay.
   */
  function Viewer(box) {
    this.box = box;
    this.canvas = box.querySelector('canvas');
    this.selectEl = box.querySelector('.atlas-select');
    this.statusEl = box.querySelector('.atlas-hint');
    this.fallbackEl = document.querySelector('.atlas-no-webgl');
    this.nv = null;
    this.ready = false;
    this.space = null;
    this.current = null;
  }

  Viewer.prototype.setStatus = function (msg) {
    if (this.statusEl) {
      this.statusEl.textContent = msg || '';
    }
  };

  Viewer.prototype.showFallback = function () {
    if (this.box) {
      this.box.style.display = 'none';
    }
    if (this.fallbackEl) {
      this.fallbackEl.style.display = '';
    }
  };

  /**
   * Swap the overlay volume for a different atlas. The template stays loaded
   * at volume index 0; only the overlay is removed and re-fetched, so at most
   * two volumes are ever in memory and only one atlas .nii.gz is in flight.
   */
  Viewer.prototype.loadAtlas = async function (space, key) {
    var spec = atlasData[space];
    var entry = spec && spec.atlases[key];
    if (!this.nv || !entry) {
      return;
    }
    this.setStatus('Loading ' + entry.display_name + '…');
    try {
      if (this.space !== space) {
        await this.nv.loadVolumes([{
          url: ATLAS_DIR + '/' + spec.template.filename,
          colormap: 'gray',
          opacity: 1
        }]);
        this.space = space;
      }
      while (this.nv.volumes.length > 1) {
        this.nv.removeVolumeByIndex(1);
      }
      await this.nv.addVolumeFromUrl({
        url: ATLAS_DIR + '/' + entry.filename,
        opacity: ATLAS_OPACITY
      });
      // NiiVue ignores a colormapLabel passed as a load option for volumes,
      // so the label LUT has to be attached to the loaded volume afterwards.
      // alphaThreshold is what actually makes value-0 voxels transparent;
      // without it the template underneath is completely hidden. It also makes
      // NiiVue ignore LUT alpha, so a coloured "Background" label (CHARM has
      // one that fills the whole volume box) is erased to 0 in the voxel data.
      var bg = {};
      entry.rows.forEach(function (r, i) {
        if (/^(background|unknown)$/i.test(r.name)) {
          bg[r.index != null ? r.index : i + 1] = true;
        }
      });
      var vol = this.nv.volumes[this.nv.volumes.length - 1];
      for (var k = 0; k < vol.img.length; k++) {
        if (bg[vol.img[k]]) {
          vol.img[k] = 0;
        }
      }
      vol.setColormapLabel(buildColormapLabel(entry.rows));
      vol.alphaThreshold = true;
      this.nv.updateGLVolume();
      this.current = space + ':' + key;
      this.setStatus(entry.display_name + ' — ' + (space === 'mni'
        ? 'MNI space, over the MNI152 template'
        : "ernie's subject space, over ernie's own T1") + '. Overlay opacity 70%.');
    } catch (e) {
      this.setStatus('Could not load ' + entry.display_name + '.');
    }
  };

  Viewer.prototype.init = async function () {
    if (!this.canvas || !this.selectEl) {
      return;
    }
    if (!hasWebGL2() || !window.niivue || !window.niivue.Niivue) {
      this.showFallback();
      return;
    }
    var self = this;
    try {
      this.nv = new window.niivue.Niivue({ isResizeCanvas: true, dragAndDropEnabled: false });
      await this.nv.attachTo(this.canvas.id);
      this.ready = true;
      var load = function () {
        var p = self.selectEl.value.split(':');
        return self.loadAtlas(p[0], p[1]);
      };
      await load();
      this.selectEl.addEventListener('change', load);
    } catch (e) {
      this.setStatus('');
      this.showFallback();
    }
  };

  /**
   * Move the crosshair to a region's centroid, switching the loaded atlas
   * first if the click came from a table for an atlas not currently shown.
   * Uses the crosshair API actually shipped in the vendored bundle
   * (scene.crosshairPos + mm2frac + updateGLVolume) - the bundle has no
   * setCrosshairPosition, and moveCrosshairInVox takes a relative voxel step
   * rather than an absolute coordinate, so neither name applies here.
   */
  Viewer.prototype.jumpTo = function (space, key, coord) {
    if (!this.nv || !this.ready) {
      return;
    }
    var self = this;
    var go = function () {
      self.nv.scene.crosshairPos = self.nv.mm2frac(coord);
      self.nv.updateGLVolume();
    };
    if (this.current !== space + ':' + key) {
      this.selectEl.value = space + ':' + key;
      this.loadAtlas(space, key).then(go);
    } else {
      go();
    }
    if (this.canvas.scrollIntoView) {
      this.canvas.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  // --- One region table, rebuilt for whichever atlas the dropdown selects ---

  function escapeRegex(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function highlightText(text, query) {
    var fragment = document.createDocumentFragment();
    if (!query) {
      fragment.append(document.createTextNode(text));
      return fragment;
    }
    var regex = new RegExp('(' + escapeRegex(query) + ')', 'gi');
    text.split(regex).forEach(function (part, index) {
      if (index % 2 === 1) {
        var mark = document.createElement('mark');
        mark.textContent = part;
        fragment.append(mark);
      } else {
        fragment.append(document.createTextNode(part));
      }
    });
    return fragment;
  }

  function wireTable(viewer) {
    var selectEl = document.getElementById('atlas-select');
    var hash = location.hash.match(/^#atlas=(\w+:\w+)$/);
    if (selectEl && hash && selectEl.querySelector('option[value="' + hash[1] + '"]')) {
      selectEl.value = hash[1];
    }
    var inputEl = document.getElementById('atlas-filter');
    var countEl = document.getElementById('atlas-count');
    var table = document.getElementById('atlas-table');
    if (!selectEl || !inputEl || !table) {
      return;
    }
    var tbody = table.tBodies[0];
    var space = null;
    var key = null;
    var rows = [];

    function applyFilter() {
      var query = inputEl.value.trim();
      var q = query.toLowerCase();
      var shown = 0;
      for (var i = 0; i < rows.length; i++) {
        var r = rows[i];
        var match = !q || r.name.toLowerCase().indexOf(q) !== -1 || String(r.id).indexOf(q) !== -1;
        r.tr.style.display = match ? '' : 'none';
        r.nameCell.replaceChildren(highlightText(r.name, query));
        if (match) {
          shown++;
        }
      }
      countEl.textContent = q ? shown + ' of ' + rows.length + ' regions' : rows.length + ' regions';
    }

    var panel = document.getElementById('atlas-desc');
    var descs = Array.prototype.slice.call(document.querySelectorAll('.atlas-desc, .atlas-note'));
    // Without JS the descriptions stay where they are in the page, all visible.
    descs.forEach(function (d) { panel.appendChild(d); });

    function build() {
      var p = selectEl.value.split(':');
      descs.forEach(function (d) {
        var on = d.getAttribute('data-atlas') === selectEl.value || d.getAttribute('data-space') === p[0];
        d.style.display = on ? '' : 'none';
      });
      space = p[0];
      key = p[1];
      var data = atlasData[space].atlases[key].rows;
      table.tHead.innerHTML = '<tr><th>ID</th><th>Name</th><th>Colour</th><th>Volume</th><th>Centroid (' +
        (space === 'mni' ? 'MNI' : 'subject') + ', mm)</th></tr>';
      tbody.textContent = '';
      rows = data.map(function (d) {
        var tr = document.createElement('tr');
        var c = d.centroid_mni.join(', ');
        tr.setAttribute('data-mni', d.centroid_mni.join(','));
        tr.innerHTML = '<td></td><td class="atlas-name"></td><td><span class="atlas-swatch"></span></td><td></td><td></td>';
        tr.cells[0].textContent = d.id;
        tr.cells[2].firstChild.style.background = 'rgb(' + d.r + ', ' + d.g + ', ' + d.b + ')';
        tr.cells[3].textContent = d.volume_mm3 + ' mm\u00b3';
        tr.cells[4].textContent = c;
        tbody.appendChild(tr);
        return { id: d.id, name: d.name, tr: tr, nameCell: tr.cells[1] };
      });
      applyFilter();
    }

    selectEl.addEventListener('change', build);
    inputEl.addEventListener('input', applyFilter);
    tbody.addEventListener('click', function (evt) {
      var row = evt.target.closest ? evt.target.closest('tr[data-mni]') : null;
      if (row) {
        viewer.jumpTo(space, key, row.getAttribute('data-mni').split(',').map(Number));
      }
    });
    build();
  }

  /**
   * Last-resort visible failure. If nothing wired up, the canvases would just
   * sit there black and the page would look broken with no explanation - which
   * is exactly what a stale cached copy of this script does against newer
   * markup. Surface it instead of failing silently.
   */
  function reportDead(reason) {
    var boxes = document.querySelectorAll('.atlas-viewer');
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].style.display = 'none';
    }
    var notes = document.querySelectorAll('.atlas-no-webgl');
    for (var j = 0; j < notes.length; j++) {
      notes[j].style.display = '';
      var p = notes[j].querySelector('p');
      if (p) {
        p.innerHTML = '<strong>Viewer could not start.</strong> ' + reason +
          ' Try a hard refresh (Cmd/Ctrl + Shift + R).';
      }
    }
  }

  function init() {
    var box = document.querySelector('.atlas-viewer');
    if (!box) {
      reportDead('The page markup and this script are out of step, most likely ' +
        'because an older copy of the script is cached.');
      return;
    }
    var viewer = new Viewer(box);
    wireTable(viewer);
    viewer.init();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
