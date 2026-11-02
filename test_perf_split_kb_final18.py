import timeit

setup = """
import re
block = \"\"\"  - "item1"
    - 'item2'
  - item3
  - "item4"
unrelated: foo
  - item5
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
    items = []
    # avoid allocating O(N) lines by using finditer to evaluate line by line, allowing us to break
    for match in re.finditer(r"^(.*)$", block, re.MULTILINE):
        raw_line = match.group(1)
        if not raw_line.startswith("  "):
            break
        item = raw_line.strip()
        if item.startswith("- "):
            items.append(strip_quotes(item[2:].strip()))
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
