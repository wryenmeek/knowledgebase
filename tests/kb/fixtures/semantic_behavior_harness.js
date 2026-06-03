const inlineScript = __INLINE_SCRIPT__;
const scenario = __SCENARIO__;
const vm = require("node:vm");

class FakeElement {
  constructor(tagName, id = null) {
    this.tagName = String(tagName || "").toLowerCase();
    this.id = id;
    this.attributes = new Map();
    this.children = [];
    this.listeners = new Map();
    this.style = {};
    this.value = "";
    this.textContent = "";
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
  }

  getAttribute(name) {
    return this.attributes.has(String(name)) ? this.attributes.get(String(name)) : null;
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this.children = [...children];
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type).push(listener);
  }

  dispatchEvent(event) {
    const eventObject = event || {};
    eventObject.type = eventObject.type || "";
    eventObject.target = eventObject.target || this;
    eventObject.preventDefault = eventObject.preventDefault || function() {};
    for (const listener of this.listeners.get(eventObject.type) || []) {
      listener(eventObject);
    }
  }
}

const elementById = new Map();
const domReadyListeners = [];
const localStorageData = new Map();
const root = new FakeElement("div", "semantic-search-root");
const pagefindInput = new FakeElement("input");
pagefindInput.className = "pagefind-ui__search-input";
root.querySelector = function(selector) {
  if (selector === "input.pagefind-ui__search-input") {
    return pagefindInput;
  }
  return null;
};

function registerElement(tagName, id) {
  const element = new FakeElement(tagName, id);
  elementById.set(id, element);
  return element;
}

registerElement("div", "pagefind-search");
const endpointInput = registerElement("input", "semantic-endpoint-input");
const endpointSaveButton = registerElement("button", "semantic-endpoint-save");
const statusNode = registerElement("p", "semantic-api-status");
const resultsNode = registerElement("ol", "semantic-results-list");
elementById.set("semantic-search-root", root);

const document = {
  getElementById(id) {
    return elementById.get(id) || null;
  },
  createElement(tagName) {
    return new FakeElement(tagName);
  }
};

let nextTimerId = 1;
const timeouts = new Map();
const intervals = new Map();

function setTimeoutStub(callback) {
  const timerId = nextTimerId;
  nextTimerId += 1;
  timeouts.set(timerId, callback);
  return timerId;
}

function clearTimeoutStub(timerId) {
  timeouts.delete(timerId);
}

function runNextTimeout() {
  const pendingIds = Array.from(timeouts.keys()).sort((left, right) => left - right);
  if (!pendingIds.length) {
    return false;
  }
  const timerId = pendingIds[0];
  const callback = timeouts.get(timerId);
  timeouts.delete(timerId);
  callback();
  return true;
}

function setIntervalStub(callback) {
  const timerId = nextTimerId;
  nextTimerId += 1;
  intervals.set(timerId, callback);
  return timerId;
}

function clearIntervalStub(timerId) {
  intervals.delete(timerId);
}

const fetchCalls = [];
const ignoreAbortForCallIndexes = scenario === "stale-response" ? new Set([0]) : new Set();
function fetchStub(url, options) {
  const callIndex = fetchCalls.length;
  const call = {
    url,
    options,
    aborted: false,
    settled: false,
    ignoreAbort: ignoreAbortForCallIndexes.has(callIndex)
  };
  fetchCalls.push(call);
  return new Promise((resolve, reject) => {
    call.resolve = (value) => {
      if (call.settled) {
        return;
      }
      call.settled = true;
      resolve(value);
    };
    call.reject = (error) => {
      if (call.settled) {
        return;
      }
      call.settled = true;
      reject(error);
    };
    const signal = options && options.signal ? options.signal : null;
    if (!signal) {
      return;
    }
    const onAbort = () => {
      call.aborted = true;
      // Keep the first stale-response request pending so the stale-guard path is exercised.
      if (call.ignoreAbort) {
        return;
      }
      call.reject({ name: "AbortError" });
    };
    if (signal.aborted) {
      onAbort();
      return;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function jsonResponse(results) {
  return {
    ok: true,
    status: 200,
    headers: {
      get(name) {
        return String(name || "").toLowerCase() === "content-type" ? "application/json" : null;
      }
    },
    json: async () => ({ results })
  };
}

async function flushMicrotasks(rounds = 5) {
  for (let index = 0; index < rounds; index += 1) {
    await Promise.resolve();
  }
}

function configureEndpoint(endpoint) {
  endpointInput.value = endpoint;
  endpointSaveButton.dispatchEvent({ type: "click" });
}

async function runStaleResponseScenario() {
  configureEndpoint("https://semantic.example.com/base");
  pagefindInput.value = "alpha query";
  pagefindInput.dispatchEvent({ type: "input", target: pagefindInput });
  if (!runNextTimeout()) {
    throw new Error("No timeout scheduled for first query");
  }
  await flushMicrotasks();
  if (fetchCalls.length !== 1) {
    throw new Error("Expected one fetch call after first query");
  }

  pagefindInput.value = "beta query";
  pagefindInput.dispatchEvent({ type: "input", target: pagefindInput });
  if (!runNextTimeout()) {
    throw new Error("No timeout scheduled for second query");
  }
  await flushMicrotasks();
  if (fetchCalls.length !== 2) {
    throw new Error("Expected two fetch calls after second query");
  }

  fetchCalls[1].resolve(
    jsonResponse([
      {
        title: "Newest semantic result",
        url: "https://knowledgebase.example/newest"
      }
    ])
  );
  await flushMicrotasks();

  fetchCalls[0].resolve(
    jsonResponse([
      {
        title: "Stale semantic result",
        url: "https://knowledgebase.example/stale"
      }
    ])
  );
  await flushMicrotasks();

  const renderedTitles = resultsNode.children
    .map((item) => {
      const firstChild = item && item.children[0] ? item.children[0] : null;
      return firstChild ? firstChild.textContent : null;
    })
    .filter((title) => typeof title === "string");
  return {
    fetchCallCount: fetchCalls.length,
    firstRequestAborted: Boolean(fetchCalls[0].options?.signal?.aborted),
    resultCount: resultsNode.children.length,
    renderedTitles,
    statusMessage: statusNode.textContent
  };
}

async function runUnsafeUrlScenario() {
  configureEndpoint("https://semantic.example.com/base");
  pagefindInput.value = "unsafe";
  pagefindInput.dispatchEvent({ type: "input", target: pagefindInput });
  if (!runNextTimeout()) {
    throw new Error("No timeout scheduled for unsafe URL query");
  }
  await flushMicrotasks();
  if (fetchCalls.length !== 1) {
    throw new Error("Expected one fetch call for unsafe URL query");
  }

  fetchCalls[0].resolve(
    jsonResponse([
      {
        title: "Unsafe semantic result",
        url: "javascript:alert('xss')"
      }
    ])
  );
  await flushMicrotasks();

  const firstItem = resultsNode.children[0] || null;
  const firstChild = firstItem && firstItem.children[0] ? firstItem.children[0] : null;
  return {
    childTag: firstChild ? firstChild.tagName : null,
    hasHref: Boolean(firstChild && typeof firstChild.href === "string" && firstChild.href),
    renderedTitle: firstChild ? firstChild.textContent : null
  };
}

const sandbox = {
  document,
  location: { origin: "https://knowledgebase.example" },
  localStorage: {
    setItem(key, value) {
      localStorageData.set(String(key), String(value));
    },
    getItem(key) {
      return localStorageData.has(String(key)) ? localStorageData.get(String(key)) : null;
    },
    removeItem(key) {
      localStorageData.delete(String(key));
    }
  },
  PagefindUI: function PagefindUI() {},
  fetch: fetchStub,
  setTimeout: setTimeoutStub,
  clearTimeout: clearTimeoutStub,
  setInterval: setIntervalStub,
  clearInterval: clearIntervalStub,
  addEventListener(eventType, listener) {
    if (eventType === "DOMContentLoaded") {
      domReadyListeners.push(listener);
    }
  },
  AbortController,
  URL,
  Promise,
  console
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.runInNewContext(inlineScript, sandbox, { timeout: 1000 });
for (const listener of domReadyListeners) {
  listener();
}

async function main() {
  await flushMicrotasks();
  if (scenario === "stale-response") {
    return runStaleResponseScenario();
  }
  if (scenario === "unsafe-url") {
    return runUnsafeUrlScenario();
  }
  throw new Error("Unknown scenario: " + scenario);
}

main()
  .then((result) => {
    process.stdout.write(JSON.stringify(result));
  })
  .catch((error) => {
    process.stderr.write(String(error && error.stack ? error.stack : error) + "\n");
    process.exit(1);
  });
