---
type: process
title: Semantic Search
status: active
updated_at: "2026-05-21T03:45:00Z"
hide:
  - navigation
  - toc
search:
  exclude: true
---

# Semantic Search

Full-text search across all wiki pages, powered by [Pagefind](https://pagefind.app).
Results include excerpts, page titles, and relevance ranking.

<link href="../pagefind/pagefind-ui.css" rel="stylesheet">
<script src="../pagefind/pagefind-ui.js"></script>

<div id="pagefind-search" style="margin-top:1.5rem;"></div>

<script>
  window.addEventListener('DOMContentLoaded', function() {
    new PagefindUI({
      element: "#pagefind-search",
      showImages: false,
      showEmptyFilters: false,
      resetStyles: false
    });
  });
</script>
