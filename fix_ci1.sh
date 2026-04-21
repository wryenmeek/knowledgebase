sed -i 's/prereq_missing:ghaw_readiness:missing_\*)/prereq_missing:ghaw_readiness:missing_* | prereq_missing:ghaw_readiness:missing_commit_sha)/g' .github/workflows/ci-1-gatekeeper.yml
sed -i '/prereq_missing:ghaw_readiness:missing_commit_sha)/d' .github/workflows/ci-1-gatekeeper.yml
sed -i '/echo "::notice::FIX: GITHUB_SHA is not set/d' .github/workflows/ci-1-gatekeeper.yml
