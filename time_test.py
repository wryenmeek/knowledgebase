import timeit

setup_without = """
from scripts.kb.page_template_utils import extract_sources_from_frontmatter
text = '''title: "Hello"
description: "World"
author: "Alice"
date: "2023-01-01"
''' * 10
"""

setup_without_opt = """
def extract_sources_from_frontmatter(frontmatter: str) -> list[str]:
    if "sources:" not in frontmatter:
        return []
    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("sources:"):
            continue
        inline_value = stripped[len("sources:"):].strip()
        if inline_value == "[]":
            return []
        if inline_value:
            return [inline_value]
        sources: list[str] = []
        for raw_line in lines[index + 1:]:
            if not raw_line.startswith("  "):
                break
            item = raw_line.strip()
            if item.startswith("- "):
                sources.append(item[2:].strip())
        return sources
    return []

text = '''title: "Hello"
description: "World"
author: "Alice"
date: "2023-01-01"
''' * 10
"""

print("Without sources (before):", timeit.timeit("extract_sources_from_frontmatter(text)", setup=setup_without, number=100000))
print("Without sources (after):", timeit.timeit("extract_sources_from_frontmatter(text)", setup=setup_without_opt, number=100000))
