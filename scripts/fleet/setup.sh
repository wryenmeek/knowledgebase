#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Setup script for fleet orchestration scripts
set -e

echo "🔧 Setting up fleet orchestration scripts..."
echo ""

# Check for Bun
if command -v bun &> /dev/null; then
  echo "✅ Bun found: $(bun --version)"
else
  echo "❌ Bun not found."
  echo "   Install Bun manually from https://bun.sh/docs/installation and re-run this script."
  exit 1
fi

echo ""

# Install dependencies
echo "📦 Installing dependencies..."
bun install
echo "✅ Dependencies installed."

echo ""

# Scaffold .env if it doesn't exist
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET_DIR="$SCRIPT_DIR"
ENV_FILE="$FLEET_DIR/.env"
ENV_EXAMPLE="$FLEET_DIR/.env.example"

if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "📝 Created .env from template. Edit it with your API keys."
  else
    echo "⚠️  No .env.example found. Create .env manually with JULES_API_KEY and GITHUB_TOKEN."
  fi
else
  echo "✅ .env already exists."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Next steps (manual):"
echo ""
echo "  1. Edit .env with your API keys:"
echo "     JULES_API_KEY=your-key-here"
echo "     GITHUB_TOKEN=your-token-here"
echo ""
echo "  2. Verify fleet workflows exist in .github/workflows/:"
echo "     - fleet-plan.yml"
echo "     - fleet-dispatch.yml"
echo "     - fleet-merge.yml"
echo ""
echo "  3. Add secrets to your GitHub repo:"
echo "     Settings → Secrets → Actions → New repository secret"
echo "     - JULES_API_KEY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
