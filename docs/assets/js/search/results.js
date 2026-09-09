/**
 * Search Results Page JavaScript
 * Handles search functionality on the dedicated search results page
 */

const BASE_URL = document.documentElement.getAttribute('data-baseurl') || '';

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
 * @returns {DocumentFragment} Text nodes with highlighted matches
 */
function highlightText(text, query) {
  const fragment = document.createDocumentFragment();
  if (!query || !text) {
    fragment.append(document.createTextNode(text || ''));
    return fragment;
  }

  // Split on literal matches; indexed content must never be parsed as HTML.
  const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
  text.split(regex).forEach((part, index) => {
    if (index % 2 === 1) {
      const mark = document.createElement('mark');
      mark.textContent = part;
      fragment.append(mark);
    } else {
      fragment.append(document.createTextNode(part));
    }
  });
  return fragment;
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

  const resultText = results.length === 1 ? 'result' : 'results';
  const stats = document.createElement('p');
  const count = document.createElement('strong');
  count.textContent = results.length;
  const searchTerm = document.createElement('em');
  searchTerm.textContent = query;
  stats.append('Found ', count, ` ${resultText} for "`, searchTerm, '"');
  statsElement.replaceChildren(stats);

  const items = results.map(result => {
    const item = document.createElement('div');
    item.className = 'search-result-item';
    const heading = document.createElement('h3');
    const link = document.createElement('a');
    link.className = 'search-result-link';
    link.append(highlightText(result.title, query));

    // Prefix the site base URL (empty for local preview, /TI-Toolbox on GitHub Pages).
    let resultUrl = result.url;
    if (!resultUrl.startsWith('http') && !resultUrl.startsWith(BASE_URL)) {
      resultUrl = BASE_URL + resultUrl;
    }
    // DOM attributes prevent quote injection; reject executable URL schemes as well.
    try {
      const parsedUrl = new URL(resultUrl, window.location.href);
      if ((parsedUrl.protocol === 'http:' || parsedUrl.protocol === 'https:') &&
          parsedUrl.origin === window.location.origin) {
        // Use the validated URL, not DOM-derived text, and keep indexed navigation
        // on this documentation origin even if the index or base attribute is altered.
        link.href = parsedUrl.href;
      }
    } catch {
      // Keep a malformed indexed URL's title readable without creating a broken link.
    }
    heading.append(link);

    const contentPreview = result.content.substring(0, 250);
    const content = document.createElement('p');
    content.className = 'search-result-content';
    content.append(highlightText(contentPreview, query));
    if (contentPreview.length === 250) content.append('...');
    item.append(heading, content);
    return item;
  });
  resultsList.replaceChildren(...items);
  noResults.style.display = 'none';
}

/**
 * Display no results message
 */
function displayNoResults() {
  const statsElement = document.getElementById('search-stats');
  const resultsList = document.getElementById('search-results-list');
  const noResults = document.getElementById('no-results');

  statsElement.replaceChildren();
  resultsList.replaceChildren();
  noResults.style.display = 'block';
}

/**
 * Navigate to search page with query
 * @param {string} query - The search query
 */
function navigateToSearch(query) {
  if (query) {
    window.location.href = `${BASE_URL}/search/?q=${encodeURIComponent(query)}`;
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
  fetch(`${BASE_URL}/search/search.json`)
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
