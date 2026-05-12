# scripts package — makes `scripts` importable as a Python package.
# For direct script invocation (python scripts/kb/lint_wiki.py), each script
# includes an inline sys.path guard:
#
#   if __package__ in (None, ""):
#       sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
#
# The guard uses parents[2] which resolves to the repo root for all files
# nested exactly two levels deep (scripts/<subdir>/<file>.py). After
# `pip install -e .`, the guard fires but has no effect since the repo root
# is already on sys.path.
