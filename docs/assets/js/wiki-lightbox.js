// Click-to-zoom lightbox for wiki content images.
(function () {
  function getCaption(img) {
    var container = img.closest('.image-container, .image-container-natural');
    if (container) {
      var em = container.querySelector('em');
      if (em) return em.innerHTML;
    }

    // Convention in wiki pages: an image sits alone in its own <p>, and the
    // very next <p> starting with bold text is its caption.
    var p = img.closest('p');
    if (p && p.nextElementSibling && p.nextElementSibling.tagName === 'P') {
      var firstChild = p.nextElementSibling.firstElementChild;
      if (firstChild && (firstChild.tagName === 'STRONG' || firstChild.tagName === 'B')) {
        return p.nextElementSibling.innerHTML;
      }
    }

    return img.getAttribute('alt') || '';
  }

  function init() {
    var content = document.querySelector('.wiki-content-inner');
    if (!content) return;

    var images = content.querySelectorAll('img');
    if (!images.length) return;

    var overlay = document.createElement('div');
    overlay.className = 'wiki-lightbox-overlay';
    overlay.innerHTML =
      '<button type="button" class="wiki-lightbox-close" aria-label="Close">&times;</button>' +
      '<div class="wiki-lightbox-content">' +
      '<img src="" alt="">' +
      '<div class="wiki-lightbox-caption"></div>' +
      '</div>';
    document.body.appendChild(overlay);

    var overlayImg = overlay.querySelector('img');
    var overlayCaption = overlay.querySelector('.wiki-lightbox-caption');
    var closeBtn = overlay.querySelector('.wiki-lightbox-close');

    function close() {
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    }

    function open(img) {
      overlayImg.src = img.currentSrc || img.src;
      overlayImg.alt = img.getAttribute('alt') || '';
      overlayCaption.innerHTML = getCaption(img);
      overlay.classList.add('active');
      document.body.style.overflow = 'hidden';
    }

    images.forEach(function (img) {
      if (img.closest('.carousel-slide')) return; // carousel has its own interaction
      img.addEventListener('click', function () {
        open(img);
      });
    });

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) close();
    });
    closeBtn.addEventListener('click', close);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
