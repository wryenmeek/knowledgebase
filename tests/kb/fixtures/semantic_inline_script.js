(function() {
  const STORAGE_KEY = "kb-semantic-search-endpoint";
  const SEARCH_PATH = "/query";
  const MIN_QUERY_LENGTH = 2;
  const SEARCH_DEBOUNCE_MS = 350;
  const RESULT_LIMIT = 5;

  function normalizeEndpoint(value) {
    return String(value || "").trim().replace(/\/+$/, "");
  }

  function sanitizeEndpoint(rawEndpoint) {
    const normalized = normalizeEndpoint(rawEndpoint);
    if (!normalized) {
      return "";
    }
    try {
      const parsed = new URL(normalized);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return "";
      }
      return normalizeEndpoint(parsed.origin + parsed.pathname);
    } catch (error) {
      return "";
    }
  }

  function sanitizeResultUrl(rawUrl) {
    if (typeof rawUrl !== "string" || !rawUrl.trim()) {
      return null;
    }
    try {
      const parsedUrl = new URL(rawUrl, window.location.origin);
      if (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:") {
        return null;
      }
      return parsedUrl.href;
    } catch (error) {
      return null;
    }
  }

  function isStorageAvailable() {
    try {
      const probe = "__kb_semantic_probe__";
      window.localStorage.setItem(probe, "1");
      window.localStorage.removeItem(probe);
      return true;
    } catch (error) {
      return false;
    }
  }

  function statusText(level, message) {
    return { level, message };
  }

  function setStatus(statusNode, status) {
    statusNode.setAttribute("data-level", status.level);
    statusNode.textContent = status.message;
  }

  function clearResults(resultsNode) {
    resultsNode.replaceChildren();
  }

  function renderResults(resultsNode, results) {
    clearResults(resultsNode);
    if (!results.length) {
      const emptyItem = document.createElement("li");
      emptyItem.textContent = "No semantic API results for the current query.";
      resultsNode.appendChild(emptyItem);
      return;
    }

    for (const result of results) {
      const item = document.createElement("li");
      const titleText = typeof result.title === "string" && result.title.trim()
        ? result.title.trim()
        : "Untitled semantic result";
      const safeUrl = sanitizeResultUrl(result.url);
      if (safeUrl) {
        const title = document.createElement("a");
        title.href = safeUrl;
        title.rel = "noopener noreferrer";
        title.textContent = titleText;
        item.appendChild(title);
      } else {
        const title = document.createElement("span");
        title.textContent = titleText;
        item.appendChild(title);
      }

      if (typeof result.snippet === "string" && result.snippet.trim()) {
        const snippet = document.createElement("p");
        snippet.style.margin = "0.25rem 0 0";
        snippet.textContent = result.snippet.trim();
        item.appendChild(snippet);
      }

      if (typeof result.score === "number" && Number.isFinite(result.score)) {
        const score = document.createElement("small");
        score.textContent = "Score: " + result.score.toFixed(3);
        item.appendChild(score);
      }

      resultsNode.appendChild(item);
    }
  }

  function resolveEndpoint(endpointInput, storageAvailable) {
    if (!storageAvailable) {
      endpointInput.value = "";
      return "";
    }

    const storedValue = sanitizeEndpoint(window.localStorage.getItem(STORAGE_KEY));
    if (!storedValue) {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    endpointInput.value = storedValue;
    return storedValue;
  }

  async function fetchSemanticResults(endpoint, query, signal) {
    const response = await fetch(endpoint + SEARCH_PATH, {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        query,
        limit: RESULT_LIMIT
      }),
      signal
    });

    if (!response.ok) {
      throw new Error("semantic_api_http_" + response.status);
    }

    const contentType = String(response.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("application/json")) {
      throw new Error("semantic_api_content_type");
    }

    let payload;
    try {
      payload = await response.json();
    } catch (error) {
      throw new Error("semantic_api_json_parse");
    }

    if (!payload || !Array.isArray(payload.results)) {
      throw new Error("semantic_api_payload_shape");
    }

    return payload.results;
  }

  function toFallbackStatus(error) {
    if (error && typeof error.message === "string" && error.message.startsWith("semantic_api_http_")) {
      return statusText(
        "warning",
        "Semantic API returned an HTTP error. Pagefind results remain available."
      );
    }
    if (error && error.message === "semantic_api_content_type") {
      return statusText(
        "warning",
        "Semantic API response was not JSON. Pagefind results remain available."
      );
    }
    if (error && error.message === "semantic_api_json_parse") {
      return statusText(
        "warning",
        "Semantic API response could not be parsed. Pagefind results remain available."
      );
    }
    if (error && error.message === "semantic_api_payload_shape") {
      return statusText(
        "warning",
        "Semantic API response was missing a results array. Pagefind results remain available."
      );
    }
    return statusText(
      "warning",
      "Semantic API is unavailable. Pagefind results remain available."
    );
  }

  function initializeSearchPage() {
    const root = document.getElementById("semantic-search-root");
    if (!root || root.getAttribute("data-initialized") === "true") {
      return;
    }
    root.setAttribute("data-initialized", "true");

    new PagefindUI({
      element: "#pagefind-search",
      showImages: false,
      showEmptyFilters: false,
      resetStyles: false
    });

    const endpointInput = document.getElementById("semantic-endpoint-input");
    const endpointSaveButton = document.getElementById("semantic-endpoint-save");
    const statusNode = document.getElementById("semantic-api-status");
    const resultsNode = document.getElementById("semantic-results-list");
    if (!endpointInput || !endpointSaveButton || !statusNode || !resultsNode) {
      return;
    }

    const storageAvailable = isStorageAvailable();
    let endpoint = resolveEndpoint(endpointInput, storageAvailable);
    let debounceTimer = null;
    let activeController = null;
    let pagefindInputBound = false;

    if (endpoint) {
      setStatus(
        statusNode,
        statusText(
          "info",
          "Semantic API endpoint configured. Pagefind results remain available."
        )
      );
    } else {
      setStatus(
        statusNode,
        statusText(
          "info",
          "Semantic API endpoint is not configured. Pagefind results remain available."
        )
      );
    }

    async function runSemanticQuery(rawQuery) {
      const query = String(rawQuery || "").trim();
      if (query.length < MIN_QUERY_LENGTH) {
        clearResults(resultsNode);
        if (!endpoint) {
          setStatus(
            statusNode,
            statusText(
              "info",
              "Semantic API endpoint is not configured. Pagefind results remain available."
            )
          );
        } else {
          setStatus(
            statusNode,
            statusText(
              "info",
              "Type at least 2 characters to query the semantic API."
            )
          );
        }
        return;
      }

      if (!endpoint) {
        clearResults(resultsNode);
        setStatus(
          statusNode,
          statusText(
            "info",
            "Semantic API endpoint is not configured. Pagefind results remain available."
          )
        );
        return;
      }

      if (activeController) {
        activeController.abort();
      }
      const controller = new AbortController();
      activeController = controller;

      setStatus(statusNode, statusText("info", "Querying semantic API..."));
      try {
        const results = await fetchSemanticResults(endpoint, query, controller.signal);
        if (activeController !== controller) {
          return;
        }
        renderResults(resultsNode, results);
        setStatus(
          statusNode,
          statusText(
            "info",
            "Semantic API query complete. Pagefind results remain available."
          )
        );
      } catch (error) {
        if (error && error.name === "AbortError") {
          return;
        }
        if (activeController !== controller) {
          return;
        }
        clearResults(resultsNode);
        setStatus(statusNode, toFallbackStatus(error));
      } finally {
        if (activeController === controller) {
          activeController = null;
        }
      }
    }

    function scheduleSemanticQuery(rawQuery) {
      if (debounceTimer) {
        window.clearTimeout(debounceTimer);
      }
      debounceTimer = window.setTimeout(function() {
        runSemanticQuery(rawQuery);
      }, SEARCH_DEBOUNCE_MS);
    }

    function bindPagefindInput() {
      if (pagefindInputBound) {
        return true;
      }
      const pagefindInput = root.querySelector("input.pagefind-ui__search-input");
      if (!pagefindInput) {
        return false;
      }
      pagefindInput.addEventListener("input", function(event) {
        scheduleSemanticQuery(event.target.value);
      });
      pagefindInput.addEventListener("search", function(event) {
        scheduleSemanticQuery(event.target.value);
      });
      pagefindInputBound = true;
      return true;
    }

    if (!bindPagefindInput()) {
      let attempts = 0;
      const maxAttempts = 40;
      const bindingInterval = window.setInterval(function() {
        attempts += 1;
        if (bindPagefindInput() || attempts >= maxAttempts) {
          window.clearInterval(bindingInterval);
        }
      }, 100);
    }

    function saveEndpoint() {
      const rawEndpoint = endpointInput.value;
      const nextEndpoint = sanitizeEndpoint(rawEndpoint);
      if (String(rawEndpoint || "").trim() && !nextEndpoint) {
        setStatus(
          statusNode,
          statusText(
            "warning",
            "Semantic API endpoint must use http or https."
          )
        );
        return;
      }

      endpoint = nextEndpoint;
      endpointInput.value = endpoint;
      clearResults(resultsNode);
      if (storageAvailable) {
        if (endpoint) {
          window.localStorage.setItem(STORAGE_KEY, endpoint);
        } else {
          window.localStorage.removeItem(STORAGE_KEY);
        }
      }

      if (!endpoint) {
        setStatus(
          statusNode,
          statusText(
            "info",
            "Semantic API endpoint cleared. Pagefind results remain available."
          )
        );
        return;
      }

      if (storageAvailable) {
        setStatus(
          statusNode,
          statusText(
            "info",
            "Semantic API endpoint saved. Pagefind results remain available."
          )
        );
      } else {
        setStatus(
          statusNode,
          statusText(
            "info",
            "Semantic API endpoint set for this page load only. Pagefind results remain available."
          )
        );
      }
    }

    endpointSaveButton.addEventListener("click", saveEndpoint);
    endpointInput.addEventListener("keydown", function(event) {
      if (event.key === "Enter") {
        event.preventDefault();
        saveEndpoint();
      }
    });
  }

  function bootstrap() {
    if (typeof window.PagefindUI === "function") {
      initializeSearchPage();
    }
  }

  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(bootstrap);
  }
  window.addEventListener("DOMContentLoaded", bootstrap);
})();
