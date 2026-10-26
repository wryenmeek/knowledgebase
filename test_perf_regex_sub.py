import timeit
import re

def f1(text):
    lines = text.splitlines()
    return "\n".join(line.rstrip() for line in lines)

def f3(text):
    return re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)

text = "key: value  \n" * 1000

print('f1:', timeit.timeit('f1(text)', globals=globals(), number=10000))
print('f3:', timeit.timeit('f3(text)', globals=globals(), number=10000))
