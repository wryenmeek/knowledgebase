import timeit
import ast
import textwrap

def f1(previous_text, current_text):
    previous_normalized = "\n".join(
        stripped for line in previous_text.splitlines() if (stripped := line.strip())
    )
    current_normalized = "\n".join(
        stripped for line in current_text.splitlines() if (stripped := line.strip())
    )
    return previous_normalized != current_normalized

def f2(previous_text, current_text):
    return previous_text.split() != current_text.split()

prev_text = "def my_func():\n  a = 1 \n  pass\n" * 1000
cur_text = "def my_func():\n  a=1\n  pass\n" * 1000

print(f1(prev_text, cur_text))
print(f2(prev_text, cur_text))
