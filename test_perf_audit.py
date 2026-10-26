import timeit

def f1(diff_output):
    return tuple(sorted({stripped for line in diff_output.splitlines() if (stripped := line.strip())}))

def f2(diff_output):
    return tuple(sorted({line for line in diff_output.split() if line}))

diff_output = "scripts/a.py\n  scripts/b.py \n \n tests/c.py\n" * 1000

print('f1:', timeit.timeit('f1(diff_output)', globals=globals(), number=10000))
print('f2:', timeit.timeit('f2(diff_output)', globals=globals(), number=10000))
