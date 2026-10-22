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

    // data-group="major" (front matter toc_group: major) folds "vN.x.y"
    // headings under one <details> per major version; only the newest is open.
    var byMajor = toc.dataset.group === 'major';
    var groups = {};
    var newestMajor = null;

    var linkMap = {};
    headings.forEach(function (h) {
      var li = document.createElement('li');
      li.className = 'docs__toc-item docs__toc-item--' + h.tagName.toLowerCase();
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent;
      li.appendChild(a);
      linkMap[h.id] = a;

      var major = byMajor && /^v(\d+)\./.exec(h.textContent.trim());
      if (!major) { list.appendChild(li); return; }
      major = major[1];
      if (newestMajor === null) newestMajor = major;
      if (!groups[major]) {
        var details = document.createElement('details');
        details.open = major === newestMajor;
        var summary = document.createElement('summary');
        summary.textContent = 'v' + major + (major === newestMajor ? '' : ' (legacy)');
        var sub = document.createElement('ul');
        details.append(summary, sub);
        var group = document.createElement('li');
        group.className = 'docs__toc-group';
        group.appendChild(details);
        list.appendChild(group);
        groups[major] = sub;
      }
      groups[major].appendChild(li);
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
        var folded = linkMap[entry.target.id].closest('details');
        if (folded) folded.open = true;
      });
    }, { rootMargin: '-90px 0px -70% 0px', threshold: 0 });
    headings.forEach(function (h) { observer.observe(h); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
