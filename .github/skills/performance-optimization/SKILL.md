---
name: performance-optimization
description: Optimizes application performance. Use when performance requirements exist, when you suspect performance regressions, or when Core Web Vitals or load times need improvement. Use when profiling reveals bottlenecks that need fixing.
---

# Performance Optimization

## Overview

Measure before optimizing. Performance work without measurement is guessing — and guessing leads to premature optimization that adds complexity without improving what matters. Profile first, identify the actual bottleneck, fix it, measure again. Optimize only what measurements prove matters.

## When to Use

- Performance requirements exist in the spec (load time budgets, response time SLAs)
- Users or monitoring report slow behavior
- Core Web Vitals scores are below thresholds
- You suspect a change introduced a regression
- Building features that handle large datasets or high traffic

**When NOT to use:** Don't optimize before you have evidence of a problem. Premature optimization adds complexity that costs more than the performance it gains.

## Core Web Vitals Targets

| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| **LCP** (Largest Contentful Paint) | ≤ 2.5s | ≤ 4.0s | > 4.0s |
| **INP** (Interaction to Next Paint) | ≤ 200ms | ≤ 500ms | > 500ms |
| **CLS** (Cumulative Layout Shift) | ≤ 0.1 | ≤ 0.25 | > 0.25 |

## The Optimization Workflow

```
1. MEASURE  → Establish baseline with real data
2. IDENTIFY → Find the actual bottleneck (not assumed)
3. FIX      → Address the specific bottleneck
4. VERIFY   → Measure again, confirm improvement
5. GUARD    → Add monitoring or tests to prevent regression
```

### Step 1: Measure

Use both synthetic and real-user measurement:

- **Synthetic (Lighthouse, DevTools Performance tab):** Controlled, reproducible. Best for CI regression detection.
- **RUM (web-vitals library, CrUX):** Real user data. Required to validate fixes actually improved experience.

See [`references/anti-pattern-examples.md`](references/anti-pattern-examples.md) for measurement setup code (web-vitals, console.time, APM).

### Where to Start Measuring

Match the symptom to the investigation:

- **Slow first load:** Check bundle size (code splitting?), TTFB (server/DNS/TLS?), render-blocking resources
- **Sluggish interactions:** Profile main thread for long tasks (>50ms), check re-renders, layout thrashing
- **Slow page navigation:** Measure API response times, check for fetch waterfalls, profile component renders
- **Backend/API slow:** Profile database queries and indexes (single endpoint) or connection pool/memory/CPU (all endpoints)

### Step 2: Identify the Bottleneck

Common bottlenecks by category:

**Frontend:**

| Symptom | Likely Cause | Investigation |
|---------|-------------|---------------|
| Slow LCP | Large images, render-blocking resources, slow server | Check network waterfall, image sizes |
| High CLS | Images without dimensions, late-loading content, font shifts | Check layout shift attribution |
| Poor INP | Heavy JavaScript on main thread, large DOM updates | Check long tasks in Performance trace |
| Slow initial load | Large bundle, many network requests | Check bundle size, code splitting |

**Backend:**

| Symptom | Likely Cause | Investigation |
|---------|-------------|---------------|
| Slow API responses | N+1 queries, missing indexes, unoptimized queries | Check database query log |
| Memory growth | Leaked references, unbounded caches, large payloads | Heap snapshot analysis |
| CPU spikes | Synchronous heavy computation, regex backtracking | CPU profiling |
| High latency | Missing caching, redundant computation, network hops | Trace requests through the stack |

### Step 3: Fix Common Anti-Patterns

Concrete examples and fixes for N+1 queries, unbounded fetching, image optimization, React re-renders, bundle size, and caching live in [`references/anti-pattern-examples.md`](references/anti-pattern-examples.md). Always measure first — copy a fix only after profiling confirms the anti-pattern is the bottleneck.

## Performance Budget

Set budgets and enforce in CI (`npx bundlesize`, `npx lhci autorun`):

- JavaScript bundle: < 200KB gzipped (initial load)
- CSS: < 50KB gzipped | Images: < 200KB per image (above fold)
- API response: < 200ms (p95) | TTI: < 3.5s on 4G | Lighthouse: ≥ 90

## See Also

For detailed performance checklists, optimization commands, and anti-pattern reference, see `references/performance-checklist.md`.


## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "We'll optimize later" | Performance debt compounds. Fix anti-patterns now, defer micro-optimizations. |
| "It's fast on my machine" | Profile on representative hardware and networks. |
| "This optimization is obvious" | If you didn't measure, you don't know. |

## Red Flags

- Optimization without profiling data to justify it
- N+1 query patterns in data fetching
- List endpoints without pagination
- Images without dimensions, lazy loading, or responsive sizes
- Bundle size growing without review
- No performance monitoring in production
- `React.memo` and `useMemo` everywhere (overusing is as bad as underusing)

## Verification

After any performance-related change:

- [ ] Before and after measurements exist (specific numbers)
- [ ] The specific bottleneck is identified and addressed
- [ ] Core Web Vitals are within "Good" thresholds
- [ ] Bundle size hasn't increased significantly
- [ ] No N+1 queries in new data fetching code
- [ ] Performance budget passes in CI (if configured)
- [ ] Existing tests still pass (optimization didn't break behavior)
