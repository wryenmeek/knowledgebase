import timeit

setup = """
out = \"\"\"M\\tscripts/foo.py
A\\tscripts/bar.py
R100\\tscripts/baz.py\\tscripts/qux.py
\"\"\" * 1000

class StagedScriptPath:
    def __init__(self, status, path, old_path):
        self.status = status
        self.path = path
        self.old_path = old_path

def _normalize_path(path: str) -> str:
    return path

def _is_scripts_python_path(path: str) -> bool:
    return True

def orig(out: str) -> list[StagedScriptPath]:
    staged = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\\t")
        if len(parts) < 2:
            return []
        status = parts[0]
        status_code = status[:1]
        path = _normalize_path(parts[-1])
        old_path = (
            _normalize_path(parts[1])
            if status_code in {"C", "R"} and len(parts) >= 3
            else None
        )
        if status_code in {"A", "C", "M", "R"} and _is_scripts_python_path(path):
            staged.append(StagedScriptPath(status=status, path=path, old_path=old_path))
    return staged

def opt(out: str) -> list[StagedScriptPath]:
    if "\\t" not in out:
        return []

    staged = []
    for line in out.split("\\n"):
        if not line:
            continue
        parts = line.split("\\t")
        if len(parts) < 2:
            return []
        status = parts[0]
        status_code = status[:1]
        path = _normalize_path(parts[-1])
        old_path = (
            _normalize_path(parts[1])
            if status_code in {"C", "R"} and len(parts) >= 3
            else None
        )
        if status_code in {"A", "C", "M", "R"} and _is_scripts_python_path(path):
            staged.append(StagedScriptPath(status=status, path=path, old_path=old_path))
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
