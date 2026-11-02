import timeit

setup = """
section_text = \"\"\"
This is some text
that doesn't have commands.
It just has words.
\"\"\" * 1000

def _is_command_like_line(raw_line: str) -> bool:
    return len(raw_line) > 50

def orig(section_text: str) -> bool:
    return any(
        _is_command_like_line(raw_line) for raw_line in section_text.splitlines()
    )

def opt(section_text: str) -> bool:
    # OPTIMIZATION: Avoid allocating O(N) line array via splitlines().
    # By using natively split string generator with '\\n' execution happens purely in C
    return any(
        _is_command_like_line(raw_line) for raw_line in section_text.split('\\n')
    )
"""

orig_code = "orig(section_text)"
opt_code = "opt(section_text)"

n = 1000
orig_time = timeit.timeit(stmt=orig_code, setup=setup, number=n)
opt_time = timeit.timeit(stmt=opt_code, setup=setup, number=n)

print(f"Orig: {orig_time:.4f}s")
print(f"Opt:  {opt_time:.4f}s")
print(f"Speedup: {orig_time / opt_time:.2f}x")
