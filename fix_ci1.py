with open(".github/workflows/ci-1-gatekeeper.yml", "r") as f:
    content = f.read()

content = content.replace("prereq_missing:ghaw_readiness:missing_*|prereq_missing:ghaw_readiness:missing_commit_sha)", "prereq_missing:ghaw_readiness:missing_commit_sha|prereq_missing:ghaw_readiness:missing_*)")

with open(".github/workflows/ci-1-gatekeeper.yml", "w") as f:
    f.write(content)
