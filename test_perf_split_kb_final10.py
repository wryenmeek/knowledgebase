import timeit

setup = """
import re
block = \"\"\"  - "item1"
    - 'item2'
  - item3
  - "item4"
\"\"\" * 1000

def orig(block: str) -> list[str]:
    items = []
    for raw_line in block.splitlines():
        if not raw_line.startswith("  "):
            break
        item = raw_line.strip()
        if item.startswith("- "):
            items.append(item[2:].strip().strip('"').strip("'"))
    return items

def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

def opt(block: str) -> list[str]:
    # Regex correctly extracts what comes after `- ` keeping inline spacing/quoting
    # stop at first line that doesn't start with 2 spaces
    items = []
    for m in re.finditer(r"^(.*?)$", block, re.MULTILINE):
        line = m.group(1)
        if not line.startswith("  "):
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(strip_quotes(stripped[2:].strip()))
    return items
"""

orig_code = "orig(block)"
opt_code = "opt(block)"

n = 1000
orig_time = timeit.timeit(stmt=orig_code, setup=setup, number=n)
opt_time = timeit.timeit(stmt=opt_code, setup=setup, number=n)

print(f"Orig: {orig_time:.4f}s")
print(f"Opt:  {opt_time:.4f}s")
print(f"Speedup: {orig_time / opt_time:.2f}x")
