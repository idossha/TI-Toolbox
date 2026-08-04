// Builds a per-page section sub-nav under the active wiki sidebar link,
// derived from the current page's own H2 headings.
(function () {
  function init() {
    var activeLink = document.querySelector('.wiki-nav a.active');
    if (!activeLink) return;

    var content = document.querySelector('.wiki-content-inner');
    if (!content) return;

    var headings = content.querySelectorAll('h2[id]');
    if (!headings.length) return;

    var subnav = document.createElement('ul');
    subnav.className = 'wiki-subnav';

    var linkMap = {};
    headings.forEach(function (h) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent;
      li.appendChild(a);
      subnav.appendChild(li);
      linkMap[h.id] = a;
    });

    var parentLi = activeLink.closest('li');
    if (!parentLi) return;
    parentLi.insertAdjacentElement('afterend', subnav);

    var headerOffset = 90;

    subnav.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (!a) return;
      e.preventDefault();
      var target = document.getElementById(a.getAttribute('href').slice(1));
      if (!target) return;
      var top = target.getBoundingClientRect().top + window.pageYOffset - headerOffset;
      window.scrollTo({ top: top, behavior: 'smooth' });
      history.pushState(null, '', '#' + target.id);
    });

    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            var link = linkMap[entry.target.id];
            if (!link) return;
            if (entry.isIntersecting) {
              Object.keys(linkMap).forEach(function (id) {
                linkMap[id].classList.remove('active-sub');
              });
              link.classList.add('active-sub');
            }
          });
        },
        { rootMargin: '-100px 0px -70% 0px', threshold: 0 }
      );
      headings.forEach(function (h) {
        observer.observe(h);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
