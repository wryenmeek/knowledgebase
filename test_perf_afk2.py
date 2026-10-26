import timeit
import re

def f1(text):
    lines = text.splitlines()
    return "\n".join(line.rstrip() for line in lines)

def f4(text):
    return "\n".join([line.rstrip() for line in text.splitlines()])

text = "title: Test   \nbody: |\n  Line 1   \n  Line 2\n" * 1000

print('f1:', timeit.timeit('f1(text)', globals=globals(), number=10000))
print('f4:', timeit.timeit('f4(text)', globals=globals(), number=10000))
