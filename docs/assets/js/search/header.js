/**
 * Header Search Box JavaScript
 * Handles search functionality in the site header
 */

(function() {
  'use strict';

  /**
   * Navigate to search page with query
   * @param {string} query - The search query
   */
  function navigateToSearch(query) {
    if (query) {
      window.location.href = `/TI-Toolbox/search/?q=${encodeURIComponent(query)}`;
    }
  }

  /**
   * Initialize header search box
   */
  function initHeaderSearch() {
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');

    if (!searchInput) {
      console.warn('Header search input not found');
      return;
    }

    // Handle Enter key in search input
    searchInput.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        const query = this.value.trim();
        navigateToSearch(query);
      }
    });

    // Handle search button click
    if (searchButton) {
      searchButton.addEventListener('click', function(e) {
        e.preventDefault();
        const query = searchInput.value.trim();
        navigateToSearch(query);
      });
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHeaderSearch);
  } else {
    initHeaderSearch();
  }
})();
