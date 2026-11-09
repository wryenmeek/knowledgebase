import timeit

def f1(path):
    parts = path.split("/")
    return path.startswith("/") or "\\" in path or ".." in parts or "" in parts

def f2(path):
    return path.startswith("/") or "\\" in path or "/../" in path or path.startswith("../") or path.endswith("/..") or "//" in path or path.endswith("/")

path = "scripts/some/very/long/path/with/many/segments/and/__pycache__/to/test/performance/script.py"

print('f1:', timeit.timeit('f1(path)', globals=globals(), number=1000000))
print('f2:', timeit.timeit('f2(path)', globals=globals(), number=1000000))

print('f1 results:')
print(f1("scripts/test.py"))
print(f1("/scripts/test.py"))
print(f1("scripts\\test.py"))
print(f1("scripts/../test.py"))
print(f1("../scripts/test.py"))
print(f1("scripts/test.py/.."))
print(f1("scripts//test.py"))
print(f1("scripts/test.py/"))
print(f1(".."))
print(f1(""))

print('f2 results:')
print(f2("scripts/test.py"))
print(f2("/scripts/test.py"))
print(f2("scripts\\test.py"))
print(f2("scripts/../test.py"))
print(f2("../scripts/test.py"))
print(f2("scripts/test.py/.."))
print(f2("scripts//test.py"))
print(f2("scripts/test.py/"))
print(f2(".."))
print(f2(""))
