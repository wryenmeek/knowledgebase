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
    # isolate the line parsing using a fast path check and split string natively
    if "\\t" not in out:
        return []
    staged = []
    for line in out.split("\\n"):
        if not line.strip():
            continue
        staged.append(line.split("\\t")[-1])
    return staged
"""

orig_code = "orig(out)"
opt_code = "opt(out)"

n = 1000
orig_time = timeit.timeit(stmt=orig_code, setup=setup, number=n)
opt_time = timeit.timeit(stmt=opt_code, setup=setup, number=n)

print(f"Orig: {orig_time:.4f}s")
print(f"Opt:  {opt_time:.4f}s")
print(f"Speedup: {orig_time / opt_time:.2f}x")
