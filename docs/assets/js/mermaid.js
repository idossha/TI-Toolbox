// Kramdown emits ```mermaid fences as <pre><code class="language-mermaid">.
// Convert them to <pre class="mermaid"> and let Mermaid render them.
(function () {
  var blocks = document.querySelectorAll('pre > code.language-mermaid');
  if (!blocks.length) return;
  blocks.forEach(function (code) {
    var pre = code.parentNode;
    var out = document.createElement('pre');
    out.className = 'mermaid';
    out.textContent = code.textContent;
    pre.parentNode.replaceChild(out, pre);
  });
  var s = document.createElement('script');
  s.type = 'module';
  s.textContent =
    "import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';" +
    "mermaid.initialize({ startOnLoad: false, theme: 'neutral' });" +
    "mermaid.run({ querySelector: 'pre.mermaid' });";
  document.head.appendChild(s);
})();
