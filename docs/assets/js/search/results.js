/**
 * Search Results Page JavaScript
 * Handles search functionality on the dedicated search results page
 */

// Global search data
let searchData = [];

/**
 * Get search query from URL parameters
 * @returns {string} The search query from URL, or empty string
 */
function getSearchQuery() {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get('q') || '';
}

/**
 * Escape special regex characters in search query
 * @param {string} text - The text to escape
 * @returns {string} Escaped text safe for regex
 */
function escapeRegex(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Highlight matching text in search results
 * @param {string} text - The text to highlight
 * @param {string} query - The search query
 * @returns {string} HTML with highlighted matches
 */
function highlightText(text, query) {
  if (!query || !text) return text;
  const escapedQuery = escapeRegex(query);
  const regex = new RegExp(`(${escapedQuery})`, 'gi');
  return text.replace(regex, '<mark>$1</mark>');
}

/**
 * Perform search on loaded data
 * @param {string} query - The search query
 */
function performSearch(query) {
  if (!query.trim()) {
    displayNoResults();
    return;
  }

  const lowerQuery = query.toLowerCase();
  const results = searchData.filter(item => {
    const titleMatch = item.title.toLowerCase().includes(lowerQuery);
    const contentMatch = item.content.toLowerCase().includes(lowerQuery);
    return titleMatch || contentMatch;
  });

  displayResults(results, query);
}

/**
 * Display search results
 * @param {Array} results - Array of search result objects
 * @param {string} query - The search query
 */
function displayResults(results, query) {
  const statsElement = document.getElementById('search-stats');
  const resultsList = document.getElementById('search-results-list');
  const noResults = document.getElementById('no-results');

  if (results.length === 0) {
    displayNoResults();
    return;
  }

  // Update stats
  const resultText = results.length === 1 ? 'result' : 'results';
  statsElement.innerHTML = `<p>Found <strong>${results.length}</strong> ${resultText} for "<em>${query}</em>"</p>`;

  // Display results
  const html = results.map(result => {
    // Highlight matching text
    const highlightedTitle = highlightText(result.title, query);
    const contentPreview = result.content.substring(0, 250);
    const highlightedContent = highlightText(contentPreview, query);

    // Construct proper URL - prepend /TI-Toolbox if not already there
    let resultUrl = result.url;
    if (!resultUrl.startsWith('http') && !resultUrl.startsWith('/TI-Toolbox')) {
      resultUrl = '/TI-Toolbox' + resultUrl;
    }

    return `
      <div class="search-result-item">
        <h3><a href="${resultUrl}" class="search-result-link">${highlightedTitle}</a></h3>
        <p class="search-result-content">${highlightedContent}${contentPreview.length === 250 ? '...' : ''}</p>
      </div>
    `;
  }).join('');

  resultsList.innerHTML = html;
  noResults.style.display = 'none';
}

/**
 * Display no results message
 */
function displayNoResults() {
  const statsElement = document.getElementById('search-stats');
  const resultsList = document.getElementById('search-results-list');
  const noResults = document.getElementById('no-results');

  statsElement.innerHTML = '';
  resultsList.innerHTML = '';
  noResults.style.display = 'block';
}

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
 * Initialize search page
 */
function initSearchPage() {
  const searchQueryInput = document.getElementById('search-query');
  const searchSubmitButton = document.getElementById('search-submit-button');

  if (!searchQueryInput || !searchSubmitButton) {
    console.error('Search page elements not found');
    return;
  }

  // Load search data
  fetch('/TI-Toolbox/search/search.json')
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      searchData = data;
      const query = getSearchQuery();
      if (query) {
        searchQueryInput.value = query;
        performSearch(query);
      }
    })
    .catch(error => {
      console.error('Error loading search data:', error);
      displayNoResults();
    });

  // Event listeners
  searchSubmitButton.addEventListener('click', function() {
    const query = searchQueryInput.value.trim();
    navigateToSearch(query);
  });

  searchQueryInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      const query = this.value.trim();
      navigateToSearch(query);
    }
  });

  // Focus on input for better UX
  searchQueryInput.focus();
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSearchPage);
} else {
  initSearchPage();
}
