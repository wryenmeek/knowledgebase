import timeit

def f1(text):
    lines = text.splitlines()
    return "\n".join(line.rstrip() for line in lines)

def f2(text):
    return "\n".join(line.rstrip() for line in text.splitlines())

text = "key: value  \n" * 1000

print('f1:', timeit.timeit('f1(text)', globals=globals(), number=100000))
print('f2:', timeit.timeit('f2(text)', globals=globals(), number=100000))
