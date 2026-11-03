// Site-wide behaviour: mobile navigation toggles.
(function () {
  function toggle(button, target) {
    if (!button || !target) return;
    button.addEventListener('click', function () {
      var open = target.classList.toggle('is-open');
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
  toggle(document.querySelector('.nav-toggle'), document.getElementById('site-nav'));
  toggle(document.querySelector('.docs__sidebar-toggle'), document.getElementById('docs-sidebar'));
  document.querySelectorAll('.sidebar-nav__toggle').forEach(function (b) {
    b.addEventListener('click', function () {
      var open = b.parentNode.classList.toggle('is-open');
      b.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  });
})();
