sed -i 's/\[ "${{ steps.diagnostics.outputs.wrapper_exit }}" -eq 0 \]/[ "${{ steps.diagnostics.outputs.wrapper_exit }}" = "0" ]/g' .github/workflows/ci-2-analyst-diagnostics.yml
sed -i 's/\[ "${{ steps.diagnostics.outputs.freshness_exit }}" -eq 0 \]/[ "${{ steps.diagnostics.outputs.freshness_exit }}" = "0" ]/g' .github/workflows/ci-2-analyst-diagnostics.yml
sed -i 's/\[ "${{ steps.diagnostics.outputs.quality_exit }}" -eq 0 \]/[ "${{ steps.diagnostics.outputs.quality_exit }}" = "0" ]/g' .github/workflows/ci-2-analyst-diagnostics.yml
sed -i 's/\[ "${{ steps.diagnostics.outputs.lint_exit }}" -eq 0 \]/[ "${{ steps.diagnostics.outputs.lint_exit }}" = "0" ]/g' .github/workflows/ci-2-analyst-diagnostics.yml
sed -i 's/\[ "${{ steps.diagnostics.outputs.tests_exit }}" -eq 0 \]/[ "${{ steps.diagnostics.outputs.tests_exit }}" = "0" ]/g' .github/workflows/ci-2-analyst-diagnostics.yml
