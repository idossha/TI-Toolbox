// Builds the "On this page" list from the article's H2/H3 headings and
// highlights the section currently in view.
(function () {
  function init() {
    var toc = document.getElementById('docs-toc');
    var list = toc && toc.querySelector('.docs__toc-list');
    var article = document.querySelector('.docs__article');
    if (!toc || !list || !article) return;

    var headings = article.querySelectorAll('h2[id], h3[id]');
    if (headings.length < 2) { toc.hidden = true; return; }

    var linkMap = {};
    headings.forEach(function (h) {
      var li = document.createElement('li');
      li.className = 'docs__toc-item docs__toc-item--' + h.tagName.toLowerCase();
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent;
      li.appendChild(a);
      list.appendChild(li);
      linkMap[h.id] = a;
    });

    var headerOffset = 80;
    list.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (!a) return;
      var target = document.getElementById(a.getAttribute('href').slice(1));
      if (!target) return;
      e.preventDefault();
      var top = target.getBoundingClientRect().top + window.pageYOffset - headerOffset;
      window.scrollTo({ top: top, behavior: 'smooth' });
      history.pushState(null, '', '#' + target.id);
    });

    if (!('IntersectionObserver' in window)) return;
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        Object.keys(linkMap).forEach(function (id) { linkMap[id].classList.remove('is-active'); });
        linkMap[entry.target.id].classList.add('is-active');
      });
    }, { rootMargin: '-90px 0px -70% 0px', threshold: 0 });
    headings.forEach(function (h) { observer.observe(h); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
