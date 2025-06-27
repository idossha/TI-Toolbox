let currentImageIndex = 0;
let images = [];

// Get all images on the page
function initializeImages() {
  const galleryImages = document.querySelectorAll('.gallery-item img');
  images = Array.from(galleryImages);
}

function openLightbox(imgElement) {
  initializeImages();
  currentImageIndex = images.indexOf(imgElement);
  updateLightboxImage();
  document.getElementById('lightbox').style.display = 'block';
  document.body.style.overflow = 'hidden'; // Prevent scrolling
}

function closeLightbox() {
  document.getElementById('lightbox').style.display = 'none';
  document.body.style.overflow = 'auto'; // Restore scrolling
}

function changeImage(direction) {
  currentImageIndex = (currentImageIndex + direction + images.length) % images.length;
  updateLightboxImage();
}

function updateLightboxImage() {
  const currentImg = images[currentImageIndex];
  const lightboxImg = document.getElementById('lightbox-img');
  const lightboxCaption = document.getElementById('lightbox-caption');
  
  lightboxImg.src = currentImg.src;
  lightboxImg.alt = currentImg.alt;
  lightboxCaption.textContent = currentImg.alt;
}

// Keyboard navigation
document.addEventListener('keydown', function(e) {
  if (document.getElementById('lightbox').style.display === 'block') {
    if (e.key === 'Escape') {
      closeLightbox();
    } else if (e.key === 'ArrowLeft') {
      changeImage(-1);
    } else if (e.key === 'ArrowRight') {
      changeImage(1);
    }
  }
});

// Initialize images when page loads
document.addEventListener('DOMContentLoaded', initializeImages); 