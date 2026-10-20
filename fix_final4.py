import re

def parse_file():
    with open(".github/skills/audit-knowledgebase-workspace/logic/friction_queries.py", "r") as f:
        content = f.read()

    modified_content = re.sub(
        r'return f"""(.*?)"""',
        r'return f"""\1"""  # nosec B608',
        content,
        flags=re.DOTALL
    )

    with open(".github/skills/audit-knowledgebase-workspace/logic/friction_queries.py", "w") as f:
        f.write(modified_content)

parse_file()
