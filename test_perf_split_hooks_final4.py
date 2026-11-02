import timeit

setup = """
import re

out = \"\"\"scripts/foo.py
scripts/bar.py
scripts/baz.py
\"\"\" * 1000

GATED_PATHS = {"scripts/foo.py", "scripts/bar.py", "scripts/baz.py"}

def _normalize_path(path: str) -> str:
    return path.strip()

def orig(out: str) -> set[str]:
    return {
        normalized
        for path in out.splitlines()
        if (normalized := _normalize_path(path)) and normalized in GATED_PATHS
    }

def opt(out: str) -> set[str]:
    return {
        normalized
        for path in out.split("\\n")
        if (normalized := _normalize_path(path)) and normalized in GATED_PATHS
    }
"""

orig_code = "orig(out)"
opt_code = "opt(out)"

n = 1000
orig_time = timeit.timeit(stmt=orig_code, setup=setup, number=n)
opt_time = timeit.timeit(stmt=opt_code, setup=setup, number=n)

print(f"Orig: {orig_time:.4f}s")
print(f"Opt:  {opt_time:.4f}s")
print(f"Speedup: {orig_time / opt_time:.2f}x")
