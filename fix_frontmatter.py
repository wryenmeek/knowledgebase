import os

filepath = "wiki/CONTEXT.md"
with open(filepath, "r") as f:
    content = f.read()

if "type:" not in content:
    content = content.replace("---", "---\ntype: context\ntitle: CONTEXT - wiki\nstatus: active\nupdated_at: 2026-04-29", 1)

with open(filepath, "w") as f:
    f.write(content)
