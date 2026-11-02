import timeit

setup = """
import re

out = \"\"\"M\\tscripts/foo.py
A\\tscripts/bar.py
R100\\tscripts/baz.py\\tscripts/qux.py
\"\"\" * 1000

def orig(out: str) -> list[str]:
    staged = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\\t")
        staged.append(parts[-1])
    return staged

def opt(out: str) -> list[str]:
    if "\\t" not in out:
        return []
    staged = []
    for match in re.finditer(r"^([^\\t\\n]*)\\t(.*)$", out, re.MULTILINE):
        parts = match.group(2).split("\\t")
        staged.append(parts[-1])
    return staged

def opt2(out: str) -> list[str]:
    if "\\t" not in out:
        return []
    return [
        match.group(1).split("\\t")[-1]
        for match in re.finditer(r"^[^\\t\\n]+\\t(.+)$", out, re.MULTILINE)
    ]
"""

orig_code = "orig(out)"
opt_code = "opt(out)"
opt2_code = "opt2(out)"

n = 1000
orig_time = timeit.timeit(stmt=orig_code, setup=setup, number=n)
opt_time = timeit.timeit(stmt=opt_code, setup=setup, number=n)
opt2_time = timeit.timeit(stmt=opt2_code, setup=setup, number=n)

print(f"Orig: {orig_time:.4f}s")
print(f"Opt:  {opt_time:.4f}s")
print(f"Opt2: {opt2_time:.4f}s")
print(f"Speedup: {orig_time / opt2_time:.2f}x")
