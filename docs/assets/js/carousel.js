function changeSlide(btn, direction) {
  const carousel = btn.closest('.carousel-container');
  const slides = carousel.querySelectorAll('.carousel-slide');
  const dots = carousel.querySelectorAll('.dot');
  let currentIndex = 0;

  // Find current active slide
  slides.forEach((slide, index) => {
    if (slide.classList.contains('active')) {
      currentIndex = index;
    }
  });

  // Remove active class from current slide
  slides[currentIndex].classList.remove('active');
  if (dots[currentIndex]) {
    dots[currentIndex].classList.remove('active');
  }

  // Calculate new index
  let newIndex = currentIndex + direction;
  if (newIndex < 0) {
    newIndex = slides.length - 1;
  } else if (newIndex >= slides.length) {
    newIndex = 0;
  }

  // Add active class to new slide
  slides[newIndex].classList.add('active');
  if (dots[newIndex]) {
    dots[newIndex].classList.add('active');
  }
}

function currentSlide(dot, index) {
  const carousel = dot.closest('.carousel-container');
  const slides = carousel.querySelectorAll('.carousel-slide');
  const dots = carousel.querySelectorAll('.dot');

  // Remove active class from all slides and dots
  slides.forEach(slide => slide.classList.remove('active'));
  dots.forEach(d => d.classList.remove('active'));

  // Add active class to selected slide and dot
  if (slides[index]) {
    slides[index].classList.add('active');
  }
  if (dots[index]) {
    dots[index].classList.add('active');
  }
}

// Auto-advance carousel
document.addEventListener('DOMContentLoaded', function() {
  const carousels = document.querySelectorAll('.carousel-container');
  carousels.forEach(carousel => {
    // Ensure at least one slide is visible on initial load
    const slides = carousel.querySelectorAll('.carousel-slide');
    if (slides.length > 0 && carousel.querySelectorAll('.carousel-slide.active').length === 0) {
      slides[0].classList.add('active');
    }

    let interval = setInterval(() => {
      const nextBtn = carousel.querySelector('.carousel-btn.next');
      if (nextBtn) {
        changeSlide(nextBtn, 1);
      }
    }, 5000); // Change slide every 5 seconds

    // Pause on hover
    carousel.addEventListener('mouseenter', () => clearInterval(interval));
    carousel.addEventListener('mouseleave', () => {
      interval = setInterval(() => {
        const nextBtn = carousel.querySelector('.carousel-btn.next');
        if (nextBtn) {
          changeSlide(nextBtn, 1);
        }
      }, 5000);
    });
  });
});

