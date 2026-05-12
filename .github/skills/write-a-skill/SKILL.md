---
name: write-a-skill
description: "Guides creation of new agent skills with correct structure, wiring, and tests. Use when creating a new skill for the .github/skills/ framework."
---

# Write a Skill

## Overview

<!-- Classification: Doc-only workflow -->

Step-by-step procedure for creating new skills that integrate correctly with the framework's discovery, routing, and testing infrastructure.

## When to Use

- Creating a new skill for `.github/skills/`
- Porting an external skill pattern into this framework
- Unsure about required skill structure or wiring steps

## Procedure

### 1. Check for overlap

Search `using-agent-skills/SKILL.md` discovery tree. If an existing skill covers the use case, extend it instead of creating a new one.

### 2. Choose routing category

- **Operator-direct**: Developer invokes directly during development workflow (e.g., `zoom-out`, `grill-me`). No persona owner needed.
- **Persona-routed**: Agent persona invokes during governance pipeline (e.g., `enforce-npov`). Must be listed in the persona's Required skills.

### 3. Create skill directory and SKILL.md

```
.github/skills/<skill-name>/SKILL.md
```

Required frontmatter:
- `name`: must match directory name exactly
- `description`: must contain "Use when..." trigger phrase

Required sections:
- `## Overview` — one-paragraph summary
- `## When to Use` — bullet list of trigger conditions
- `## Procedure` or `## Rules` — step-by-step workflow or rule set
- `## Verification` — how to confirm the skill was applied correctly

Size target: ≤ 100 lines.

### 4. Add logic (if write-capable)

If the skill performs repository writes:
1. Create `logic/` subdirectory with Python module
2. Follow `_optional_surface_common.py` pattern (`SurfaceResult`, `JsonArgumentParser`, `run_surface_cli`)
3. Declare in AGENTS.md write-surface matrix
4. Add lock requirements and hard-fail conditions to SKILL.md

### 5. Wire into framework

1. Add to `using-agent-skills/SKILL.md` discovery tree
2. Add to `.github/copilot-instructions.md` lifecycle mapping and intent mapping
3. If persona-routed: add to the relevant agent persona's Required skills

### 6. Update tests

1. `tests/kb/test_framework_skills.py` — skill name appears in framework validation
2. If write-capable: `tests/kb/test_framework_write_surface_matrix.py` — matrix row exists

## Verification

1. `name` in frontmatter matches directory name.
2. `description` contains "Use when".
3. File is ≤ 100 lines.
4. Skill appears in `using-agent-skills` discovery tree.
5. `python3 -m pytest tests/kb/test_framework_skills.py -v` passes.
