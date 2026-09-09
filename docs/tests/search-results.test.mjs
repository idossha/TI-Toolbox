// Run: node --test docs/tests/search-results.test.mjs (uses desktop's installed jsdom).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(new URL('../../desktop/package.json', import.meta.url));
const { JSDOM } = require('jsdom');
const source = readFileSync(new URL('../assets/js/search/results.js', import.meta.url), 'utf8');

async function search(t, query, data, base = '/TI-Toolbox') {
  const dom = new JSDOM(`<!doctype html><html><body>
    <input id="search-query"><button id="search-submit-button">Search</button>
    <div id="search-stats"></div><div id="search-results-list"></div>
    <div id="no-results" style="display:none">No results found</div>
  </body></html>`, {
    url: `https://example.test${base}/search/?q=${encodeURIComponent(query)}`,
    runScripts: 'outside-only',
  });
  t.after(() => dom.window.close());
  dom.window.document.documentElement.setAttribute('data-baseurl', base);
  dom.window.fetch = async () => ({ ok: true, json: async () => data });
  dom.window.eval(source);
  // Let DOMContentLoaded and the mocked fetch/json promises finish.
  await new Promise(resolve => setImmediate(resolve));
  return dom.window;
}

function assertOnlyTextMarkup(document) {
  const rendered = document.querySelector('#search-results-container') || document.body;
  assert.equal(rendered.querySelectorAll('img, svg, script, iframe').length, 0);
  for (const element of rendered.querySelectorAll('*')) {
    assert.equal(element.getAttributeNames().some(name => /^on/i.test(name)), false);
  }
}

test('markup-like URL query stays text in statistics and highlighted content', async t => {
  const query = '<img src=x onerror="alert(1)">';
  const window = await search(t, query, [{ title: 'A result', content: query, url: '/wiki/a/' }]);
  const doc = window.document;
  assert.equal(doc.querySelector('#search-stats em').textContent, query);
  assert.equal(doc.querySelector('.search-result-content mark').textContent, query);
  assertOnlyTextMarkup(doc);
});

test('indexed title and snippet markup stays literal, including unmatched text', async t => {
  const title = '<svg onload="alert(1)">Brain</svg>';
  const content = 'Brain <img src=x onerror="alert(1)"> & tissue';
  const window = await search(t, 'brain', [{ title, content, url: '/wiki/brain/' }]);
  const doc = window.document;
  assert.equal(doc.querySelector('.search-result-link').textContent, title);
  assert.equal(doc.querySelector('.search-result-content').textContent, content);
  assert.deepEqual(Array.from(doc.querySelectorAll('mark'), node => node.textContent), ['Brain', 'Brain']);
  assertOnlyTextMarkup(doc);
});

test('ordinary matches preserve casing, literal regex characters, count and links', async t => {
  const window = await search(t, 'TI+', [
    { title: 'TI+ and ti+', content: 'Use Ti+ here', url: '/wiki/ti/' },
    { title: 'TI+ remote', content: 'reference', url: 'https://reference.test/ti/' },
  ]);
  const doc = window.document;
  assert.equal(doc.querySelector('#search-stats').textContent, 'Found 2 results for "TI+"');
  assert.deepEqual(Array.from(doc.querySelectorAll('mark'), node => node.textContent), ['TI+', 'ti+', 'Ti+', 'TI+']);
  assert.deepEqual(Array.from(doc.querySelectorAll('.search-result-link'), node => node.href),
    ['https://example.test/TI-Toolbox/wiki/ti/', 'https://reference.test/ti/']);
  assert.equal(doc.querySelector('#no-results').style.display, 'none');
});

test('snippet length and singular statistics stay unchanged', async t => {
  const content = 'match ' + 'x'.repeat(300);
  const window = await search(t, 'match', [{ title: 'match', content, url: '/TI-Toolbox/wiki/a/' }]);
  const doc = window.document;
  assert.equal(doc.querySelector('#search-stats').textContent, 'Found 1 result for "match"');
  assert.equal(doc.querySelector('.search-result-content').textContent, content.slice(0, 250) + '...');
  assert.equal(doc.querySelector('a').getAttribute('href'), '/TI-Toolbox/wiki/a/');
});

test('no matches and whitespace query clear previous results', async t => {
  const window = await search(t, 'match', [{ title: 'match', content: 'body', url: '/wiki/a/' }]);
  for (const query of ['not found', '   ']) {
    window.performSearch(query);
    assert.equal(window.document.querySelector('#search-stats').textContent, '');
    assert.equal(window.document.querySelector('#search-results-list').children.length, 0);
    assert.equal(window.document.querySelector('#no-results').style.display, 'block');
  }
});

test('empty URL query preserves the initial empty search state', async t => {
  const window = await search(t, '', []);
  assert.equal(window.document.querySelector('#search-results-list').children.length, 0);
  assert.equal(window.document.querySelector('#search-stats').textContent, '');
  assert.equal(window.document.querySelector('#no-results').style.display, 'none');
});

test('result URLs cannot add attributes or execute script on a root-base preview', async t => {
  const window = await search(t, 'match', [
    { title: 'match unsafe scheme', content: '', url: 'javascript:alert(1)' },
    { title: 'match quote', content: '', url: '/wiki/" onclick="alert(1)' },
  ], '');
  const links = Array.from(window.document.querySelectorAll('.search-result-link'));
  assert.equal(links.length, 2);
  assert.equal(links[0].hasAttribute('href'), false);
  assert.equal(links[1].hasAttribute('onclick'), false);
  assert.equal(new URL(links[1].href).protocol, 'https:');
  assertOnlyTextMarkup(window.document);
});
