// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import fs from 'node:fs'
import { JULES_API_KEY, GITHUB_TOKEN } from "./env.js";
import { jules } from '@google/jules-sdk'
import { analyzeIssuesPrompt } from './prompts/analyze-issues.js'
import { getIssuesAsMarkdown } from './github/markdown.js'
import { getGitRepoInfo, getCurrentBranch } from './github/git.js'

const repoInfo = await getGitRepoInfo()
const baseBranch = process.env.FLEET_BASE_BRANCH ?? await getCurrentBranch()
const issuesMarkdown = await getIssuesAsMarkdown()
const prompt = analyzeIssuesPrompt({ issuesMarkdown, repoFullName: repoInfo.fullName })

console.log(`🔍 Planning fleet for ${repoInfo.fullName} (branch: ${baseBranch})`)

// jules.run() auto-approves the plan and auto-creates a PR (autoPr defaults to true).
// jules.session() would pause waiting for manual plan approval — wrong for CI.
const run = await jules.run({
  prompt,
  source: {
    github: repoInfo.fullName,
    baseBranch,
  },
})

console.log(`✅ Planning run started: ${run.id}`)

// Export session ID for the downstream "Wait for planning PR" CI step.
if (process.env.GITHUB_OUTPUT) {
  fs.appendFileSync(process.env.GITHUB_OUTPUT, `plan_session_id=${run.id}\n`)
}
