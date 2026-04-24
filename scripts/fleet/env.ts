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

import * as util from "util";

export const JULES_API_KEY = process.env.JULES_API_KEY;
export const GITHUB_TOKEN = process.env.GITHUB_TOKEN;

if (!JULES_API_KEY) {
  console.error("❌ JULES_API_KEY environment variable is required.");
  process.exit(1);
}

if (!GITHUB_TOKEN) {
  console.error("❌ GITHUB_TOKEN environment variable is required.");
  process.exit(1);
}

// Redact sensitive tokens from console outputs to prevent accidental exposure
const originalLog = console.log;
const originalError = console.error;

function redact(text: string): string {
  let redacted = text;
  if (JULES_API_KEY) redacted = redacted.replaceAll(JULES_API_KEY, "***REDACTED_JULES_API_KEY***");
  if (GITHUB_TOKEN) redacted = redacted.replaceAll(GITHUB_TOKEN, "***REDACTED_GITHUB_TOKEN***");
  return redacted;
}

console.log = (...args: any[]) => {
  const formatted = util.format(...args);
  const redacted = redact(formatted);
  process.stdout.write(redacted + '\n');
};

console.error = (...args: any[]) => {
  const formatted = util.format(...args);
  const redacted = redact(formatted);
  process.stderr.write(redacted + '\n');
};
