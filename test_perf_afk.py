import timeit
import re

def f1(text):
    lines = text.splitlines()
    return "\n".join(line.rstrip() for line in lines)

def f2(text):
    # This avoids duplicate memory allocation for `lines` by feeding the generator
    # directly from splitlines without creating the intermediate Python variable holding the list.
    return "\n".join(line.rstrip() for line in text.splitlines())

def f3(text):
    # Use re.sub to remove trailing whitespaces on each line.
    return re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)

text = "title: Test   \nbody: |\n  Line 1   \n  Line 2\n" * 1000

print('f1:', timeit.timeit('f1(text)', globals=globals(), number=10000))
print('f2:', timeit.timeit('f2(text)', globals=globals(), number=10000))
print('f3:', timeit.timeit('f3(text)', globals=globals(), number=10000))
