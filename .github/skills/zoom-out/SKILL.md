---
name: zoom-out
description: "Maps the relevant modules, callers, and abstractions around unfamiliar code or wiki areas. Use when entering unfamiliar territory, when you need to understand how components connect, or when context is unclear before diving into implementation."
---

# Zoom Out

## Overview

Before diving into implementation, map the territory. Understand the module graph, callers, and abstractions around the area you'll be working in. This prevents narrow fixes that break upstream consumers or miss existing helpers.

## When to Use

- Entering unfamiliar code or wiki namespace
- Joining a new area of the codebase
- Before a significant refactor
- When context is unclear and you're tempted to start editing immediately

## Procedure

### 1. Code Context

1. Identify the module under focus.
2. List its direct callers and callees.
3. Map one level of abstraction up (who uses this?) and one level down (what does this use?).
4. Note boundary interfaces — public API, exports, shared types, `__all__` entries.
5. Check canonical utility modules (`page_template_utils`, `write_utils`, `contracts`, `_optional_surface_common`) for existing helpers before writing new ones.

### 2. Governance Context (KB-specific)

1. Identify relevant entries in `AGENTS.md` — especially the write-surface matrix row for the area.
2. Check if the area touches a governed path (`wiki/**`, `raw/processed/**`, `schema/**`).
3. Note which skills and agent personas own adjacent functionality.
4. Confirm lock requirements and fail-closed behavior for any write paths.

## Output

A brief orientation map (5–10 bullet points) covering:
- Module under focus and its role
- Key callers and callees
- Boundary interfaces
- Governed paths and lock requirements
- Adjacent skills/agents
- Existing helpers that apply

Reference this map throughout the session to stay oriented.

> Doc-only workflow. Inspired by mattpocock/skills `zoom-out`. KB variant adds governance orientation.
