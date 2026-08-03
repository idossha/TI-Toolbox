/**
 * Atlas Browser page script (docs/wiki/atlases.md only).
 *
 * Mounts a vendored NiiVue viewer on a canvas, draws the MNI152 template as
 * a grayscale base layer, and overlays one of four MNI-space atlases at a
 * time as a sparse label colormap. Label metadata (id/name/colour/centroid)
 * is read from a JSON blob the page embeds inline (Jekyll does not publish
 * _data/ as a URL, so the data cannot be fetched separately).
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
  var TEMPLATE_URL = ATLAS_DIR + '/mni152_t1_1mm.nii.gz';
  var ATLAS_OPACITY = 0.7;

  var canvas = document.getElementById('atlas-canvas');
  var viewerBox = document.getElementById('atlas-viewer');
  var selectEl = document.getElementById('atlas-select');
  var statusEl = document.getElementById('atlas-status');
  var fallbackEl = document.getElementById('atlas-no-webgl');
  var dataEl = document.getElementById('atlas-data');

  if (!canvas || !selectEl || !dataEl) {
    // Required markup missing - nothing to wire up.
    return;
  }

  var atlasData = null;
  try {
    atlasData = JSON.parse(dataEl.textContent);
  } catch (e) {
    setStatus('Could not read atlas label data.');
    return;
  }

  var nv = null;
  var atlasReady = false; // true once the template volume has loaded

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

  function setStatus(msg) {
    if (statusEl) {
      statusEl.textContent = msg || '';
    }
  }

  /**
   * Build the {R, G, B, I, labels} colormap NiiVue's makeLabelLut() expects.
   * All four arrays are the same length as the atlas's row list (one entry
   * per labelled region) - the I array is left sparse on purpose so
   * Glasser's 1-180 / 1001-1180 scheme does not need a dense 0..1180 table.
   */
  function buildColormapLabel(key) {
    var rows = atlasData[key].rows;
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
      I.push(rows[i].id);
      labels.push(rows[i].name);
    }
    return { R: R, G: G, B: B, A: A, I: I, labels: labels };
  }

  /**
   * Swap the overlay volume for a different atlas. The template stays
   * loaded at volume index 0; only the overlay (index 1, if present) is
   * removed and re-fetched, so at most two volumes are ever in memory and
   * only one atlas .nii.gz is fetched at a time.
   */
  async function loadAtlas(key) {
    var entry = atlasData[key];
    if (!nv || !entry) {
      return;
    }
    setStatus('Loading ' + entry.display_name + '...');
    try {
      while (nv.volumes.length > 1) {
        nv.removeVolumeByIndex(1);
      }
      await nv.addVolumeFromUrl({
        url: ATLAS_DIR + '/' + entry.filename,
        opacity: ATLAS_OPACITY
      });
      // NiiVue ignores a colormapLabel passed as a load option for volumes,
      // so the label LUT has to be attached to the loaded volume afterwards.
      // alphaThreshold is what actually makes value-0 voxels transparent;
      // without it the template underneath is completely hidden.
      var vol = nv.volumes[nv.volumes.length - 1];
      vol.setColormapLabel(buildColormapLabel(key));
      vol.alphaThreshold = true;
      nv.updateGLVolume();
      setStatus('');
    } catch (e) {
      setStatus('Could not load ' + entry.display_name + '.');
    }
  }

  async function initViewer() {
    if (!hasWebGL2() || !window.niivue || !window.niivue.Niivue) {
      showFallback();
      return;
    }
    try {
      nv = new window.niivue.Niivue({ isResizeCanvas: true, dragAndDropEnabled: false });
      await nv.attachTo('atlas-canvas');
      setStatus('Loading template...');
      await nv.loadVolumes([{ url: TEMPLATE_URL, colormap: 'gray', opacity: 1 }]);
      atlasReady = true;
      await loadAtlas(selectEl.value || Object.keys(atlasData)[0]);
    } catch (e) {
      setStatus('');
      showFallback();
    }
  }

  function showFallback() {
    if (viewerBox) {
      viewerBox.style.display = 'none';
    }
    if (fallbackEl) {
      fallbackEl.style.display = '';
    }
  }

  /**
   * Move the crosshair to a region's MNI centroid, switching the loaded
   * atlas first if the click came from a table for an atlas that is not
   * currently on screen. Uses the crosshair API actually shipped in the
   * vendored bundle (scene.crosshairPos + mm2frac + updateGLVolume) - the
   * bundle has no setCrosshairPosition method and moveCrosshairInVox takes
   * a relative voxel step, not an absolute coordinate, so neither name
   * applies here.
   */
  function jumpToRegion(atlasKey, mni) {
    if (!nv || !atlasReady) {
      return;
    }
    var go = function () {
      nv.scene.crosshairPos = nv.mm2frac(mni);
      nv.updateGLVolume();
    };
    if (selectEl.value !== atlasKey) {
      selectEl.value = atlasKey;
      loadAtlas(atlasKey).then(go);
    } else {
      go();
    }
    if (canvas.scrollIntoView) {
      canvas.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  // --- Table filter: copied pattern from assets/js/search/results.js ---

  function escapeRegex(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function highlightText(text, query) {
    if (!query) {
      return text;
    }
    var escapedQuery = escapeRegex(query);
    var regex = new RegExp('(' + escapedQuery + ')', 'gi');
    return text.replace(regex, '<mark>$1</mark>');
  }

  function wireFilter(inputEl, tableEl) {
    var rows = Array.prototype.slice.call(tableEl.querySelectorAll('tbody tr'));
    var nameCells = rows.map(function (row) {
      return row.querySelector('.atlas-name');
    });
    var originalNames = nameCells.map(function (cell) {
      return cell ? cell.textContent : '';
    });

    inputEl.addEventListener('input', function () {
      var query = inputEl.value.trim();
      var lowerQuery = query.toLowerCase();
      for (var i = 0; i < rows.length; i++) {
        var id = rows[i].getAttribute('data-id') || '';
        var name = originalNames[i] || '';
        var match = !lowerQuery || name.toLowerCase().indexOf(lowerQuery) !== -1 || id.indexOf(lowerQuery) !== -1;
        rows[i].style.display = match ? '' : 'none';
        if (nameCells[i]) {
          nameCells[i].innerHTML = highlightText(originalNames[i], query);
        }
      }
    });
  }

  // --- Wire up row clicks for every atlas table on the page ---

  function wireRowClicks() {
    var tables = document.querySelectorAll('table[data-atlas]');
    for (var t = 0; t < tables.length; t++) {
      (function (table) {
        var atlasKey = table.getAttribute('data-atlas');
        table.addEventListener('click', function (evt) {
          var row = evt.target.closest ? evt.target.closest('tr[data-mni]') : null;
          if (!row || !table.contains(row)) {
            return;
          }
          var mni = row.getAttribute('data-mni').split(',').map(Number);
          jumpToRegion(atlasKey, mni);
        });
      })(tables[t]);
    }
  }

  function wireFilters() {
    var inputs = document.querySelectorAll('input.atlas-filter[data-target]');
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      var table = document.getElementById(input.getAttribute('data-target'));
      if (table) {
        wireFilter(input, table);
      }
    }
  }

  function wireSelect() {
    selectEl.addEventListener('change', function () {
      loadAtlas(selectEl.value);
    });
  }

  function init() {
    wireFilters();
    wireRowClicks();
    wireSelect();
    initViewer();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
