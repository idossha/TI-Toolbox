---
layout: default
title: Search Results
permalink: /search/
---

<div class="search-page">
  <div class="search-header">
    <h1>Search Results</h1>
    <div class="search-input-container">
      <input type="text" id="search-query" placeholder="Search documentation..." class="search-input-large">
      <button id="search-submit-button" class="search-button">Search</button>
    </div>
  </div>

  <div id="search-results-container" class="search-results-container">
    <div id="search-stats" class="search-stats"></div>
    <div id="search-results-list" class="search-results-list"></div>
    <div id="no-results" class="no-results" style="display: none;">
      <p>No results found for your search query.</p>
      <p>Try different keywords or check your spelling.</p>
    </div>
  </div>
</div>

<script src="{{ "/assets/js/search/results.js" | relative_url }}"></script>
