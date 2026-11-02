import timeit

setup = """
diff_output = \"\"\"file1.txt
  file2.txt
file3.txt

file1.txt
file4.txt
\"\"\" * 1000

def orig(diff_output: str) -> tuple[str, ...]:
    return tuple(
        sorted({stripped for line in diff_output.splitlines() if (stripped := line.strip())})
    )

def opt(diff_output: str) -> tuple[str, ...]:
    return tuple(
        sorted({line for line in diff_output.split()})
    )
"""

orig_code = "orig(diff_output)"
opt_code = "opt(diff_output)"

n = 1000
orig_time = timeit.timeit(stmt=orig_code, setup=setup, number=n)
opt_time = timeit.timeit(stmt=opt_code, setup=setup, number=n)

print(f"Orig: {orig_time:.4f}s")
print(f"Opt:  {opt_time:.4f}s")
print(f"Speedup: {orig_time / opt_time:.2f}x")
