from pathlib import Path
import time

def read_small():
    return Path(".gitignore").read_text(encoding="utf-8").splitlines()

def read_small_opt():
    with open(".gitignore", encoding="utf-8") as f:
        return f.read().splitlines()

t0 = time.time()
for _ in range(1000):
    read_small()
t1 = time.time()

t2 = time.time()
for _ in range(1000):
    read_small_opt()
t3 = time.time()

print("Original:", t1 - t0)
print("Opt:", t3 - t2)
