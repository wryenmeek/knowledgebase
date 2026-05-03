import sys
import yaml
from pathlib import Path
from scripts.kb.page_template_utils import parse_frontmatter

repo_root = Path(".")
context_file = repo_root / "wiki" / "CONTEXT.md"
if not context_file.exists():
    print(f"{context_file} does not exist")
    sys.exit(1)

content = context_file.read_text()
fm, body = parse_frontmatter(content)
print(fm)
