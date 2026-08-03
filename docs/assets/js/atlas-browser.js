/**
 * Atlas Browser page script (docs/wiki/atlases.md only).
 *
 * Drives one independent NiiVue viewer per coordinate space. Each viewer
 * draws its own template as a grayscale base layer and overlays one atlas at
 * a time as a sparse label colormap. Label metadata (id/name/colour/centroid)
 * is read from a JSON blob the page embeds inline (Jekyll does not publish
 * _data/ as a URL, so the data cannot be fetched separately).
 *
 * Expected markup, per space:
 *   <div class="atlas-viewer" data-space="mni">
 *     <select class="atlas-select" data-space="mni">...</select>
 *     <span class="atlas-status" data-space="mni"></span>
 *     <canvas id="atlas-canvas-mni"></canvas>
 *   </div>
 *   <div class="atlas-no-webgl" data-space="mni" style="display:none">...</div>
 *   <table data-space="mni" data-atlas="cit168"> ... <tr data-mni="x,y,z">
 *
 * Table filtering copies the case-insensitive substring + <mark> highlight
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
  function Viewer(space, box) {
    this.space = space;
    this.box = box;
    this.spec = atlasData[space];
    this.canvas = box.querySelector('canvas');
    this.selectEl = box.querySelector('.atlas-select');
    this.statusEl = box.querySelector('.atlas-status');
    this.fallbackEl = document.querySelector('.atlas-no-webgl[data-space="' + space + '"]');
    this.nv = null;
    this.ready = false;
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
  Viewer.prototype.loadAtlas = async function (key) {
    var entry = this.spec && this.spec.atlases[key];
    if (!this.nv || !entry) {
      return;
    }
    this.setStatus('Loading ' + entry.display_name + '…');
    try {
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
      // without it the template underneath is completely hidden.
      var vol = this.nv.volumes[this.nv.volumes.length - 1];
      vol.setColormapLabel(buildColormapLabel(entry.rows));
      vol.alphaThreshold = true;
      this.nv.updateGLVolume();
      this.current = key;
      this.setStatus('');
    } catch (e) {
      this.setStatus('Could not load ' + entry.display_name + '.');
    }
  };

  Viewer.prototype.init = async function () {
    if (!this.canvas || !this.selectEl || !this.spec) {
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
      this.setStatus('Loading template…');
      await this.nv.loadVolumes([{
        url: ATLAS_DIR + '/' + this.spec.template.filename,
        colormap: 'gray',
        opacity: 1
      }]);
      this.ready = true;
      await this.loadAtlas(this.selectEl.value || Object.keys(this.spec.atlases)[0]);
      this.selectEl.addEventListener('change', function () {
        self.loadAtlas(self.selectEl.value);
      });
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
  Viewer.prototype.jumpTo = function (key, coord) {
    if (!this.nv || !this.ready) {
      return;
    }
    var self = this;
    var go = function () {
      self.nv.scene.crosshairPos = self.nv.mm2frac(coord);
      self.nv.updateGLVolume();
    };
    if (this.current !== key) {
      this.selectEl.value = key;
      this.loadAtlas(key).then(go);
    } else {
      go();
    }
    if (this.canvas.scrollIntoView) {
      this.canvas.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  // --- Table filter: copied pattern from assets/js/search/results.js ---

  function escapeRegex(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function highlightText(text, query) {
    if (!query) {
      return text;
    }
    var regex = new RegExp('(' + escapeRegex(query) + ')', 'gi');
    return text.replace(regex, '<mark>$1</mark>');
  }

  function wireFilter(inputEl, tableEl, countEl) {
    var rows = Array.prototype.slice.call(tableEl.querySelectorAll('tbody tr'));
    var nameCells = rows.map(function (row) {
      return row.querySelector('.atlas-name');
    });
    var originalNames = nameCells.map(function (cell) {
      return cell ? cell.textContent : '';
    });
    var total = rows.length;

    inputEl.addEventListener('input', function () {
      var query = inputEl.value.trim();
      var lowerQuery = query.toLowerCase();
      var shown = 0;
      for (var i = 0; i < rows.length; i++) {
        var id = rows[i].getAttribute('data-id') || '';
        var name = originalNames[i] || '';
        var match = !lowerQuery || name.toLowerCase().indexOf(lowerQuery) !== -1 || id.indexOf(lowerQuery) !== -1;
        rows[i].style.display = match ? '' : 'none';
        if (match) {
          shown++;
        }
        if (nameCells[i]) {
          nameCells[i].innerHTML = highlightText(originalNames[i], query);
        }
      }
      if (countEl) {
        countEl.textContent = lowerQuery
          ? shown + ' of ' + total + ' regions'
          : total + ' regions';
      }
    });
  }

  function wireFilters() {
    var inputs = document.querySelectorAll('input.atlas-filter[data-target]');
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      var table = document.getElementById(input.getAttribute('data-target'));
      var countEl = input.parentNode
        ? input.parentNode.querySelector('.atlas-count')
        : null;
      if (table) {
        wireFilter(input, table, countEl);
      }
    }
  }

  // --- Wire up row clicks for every atlas table on the page ---

  function wireRowClicks(viewers) {
    var tables = document.querySelectorAll('table[data-atlas]');
    for (var t = 0; t < tables.length; t++) {
      (function (table) {
        var atlasKey = table.getAttribute('data-atlas');
        var space = table.getAttribute('data-space');
        table.addEventListener('click', function (evt) {
          var row = evt.target.closest ? evt.target.closest('tr[data-mni]') : null;
          if (!row || !table.contains(row)) {
            return;
          }
          var viewer = viewers[space];
          if (!viewer) {
            return;
          }
          viewer.jumpTo(atlasKey, row.getAttribute('data-mni').split(',').map(Number));
        });
      })(tables[t]);
    }
  }

  function init() {
    var viewers = {};
    var boxes = document.querySelectorAll('.atlas-viewer[data-space]');
    for (var i = 0; i < boxes.length; i++) {
      var space = boxes[i].getAttribute('data-space');
      if (atlasData[space]) {
        viewers[space] = new Viewer(space, boxes[i]);
      }
    }
    wireFilters();
    wireRowClicks(viewers);
    Object.keys(viewers).forEach(function (k) {
      viewers[k].init();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
