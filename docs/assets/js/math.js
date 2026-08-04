// KaTeX auto-render bootstrap.
//
// Authoring contract for the Markdown sources:
//   inline   ->  $$E_1$$          (kramdown turns this into \( ... \))
//   display  ->  $$\n ... \n$$    (kramdown turns this into \[ ... \])
//
// Kramdown parses the math itself, so the body is passed through verbatim and is
// never mangled by Markdown emphasis/escaping rules. Never write a bare `|` inside
// math that lives in a table cell -- use \lvert / \rvert / \mid.
//
// Runs on DOMContentLoaded, which fires after the deferred katex + auto-render
// scripts have executed, so load order is guaranteed by `defer` alone.

(function () {
  function renderMath() {
    if (typeof renderMathInElement !== 'function') {
      return; // KaTeX blocked (offline / CDN failure) -- leave the source visible.
    }

    renderMathInElement(document.body, {
      delimiters: [
        { left: '\\[', right: '\\]', display: true },
        { left: '\\(', right: '\\)', display: false },
        // Fallback for math written inside raw HTML blocks, which kramdown
        // passes through untouched.
        { left: '$$', right: '$$', display: true }
      ],
      // Never typeset inside code -- the docs are full of shell snippets
      // containing $HOME, ${VAR} and the like.
      ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option'],
      ignoredClasses: ['no-math', 'highlight', 'highlighter-rouge'],
      // Show the offending source in red rather than throwing, so one bad
      // expression cannot blank out the rest of the page.
      throwOnError: false,
      errorColor: '#c0392b',
      strict: false,
      trust: false,
      macros: {
        // Upright multi-letter quantity names used throughout the wiki.
        '\\MD': '\\mathrm{MD}',
        '\\ROI': '\\mathrm{ROI}',
        '\\nonROI': '\\mathrm{non\\text{-}ROI}',
        '\\Vm': '\\mathrm{V/m}'
      }
    });

    document.documentElement.classList.add('katex-ready');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderMath);
  } else {
    renderMath();
  }
})();
