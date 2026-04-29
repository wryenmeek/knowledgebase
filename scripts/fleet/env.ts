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

import util from "node:util";

export const JULES_API_KEY = process.env.JULES_API_KEY;
export const GITHUB_TOKEN = process.env.GITHUB_TOKEN;

if (!JULES_API_KEY) {
  process.stderr.write("❌ JULES_API_KEY environment variable is required.\n");
  process.exit(1);
}

if (!GITHUB_TOKEN) {
  process.stderr.write("❌ GITHUB_TOKEN environment variable is required.\n");
  process.exit(1);
}

function redact(str: string): string {
  let redacted = str;
  if (JULES_API_KEY) {
    redacted = redacted.replaceAll(JULES_API_KEY, "[REDACTED_JULES_API_KEY]");
  }
  if (GITHUB_TOKEN) {
    redacted = redacted.replaceAll(GITHUB_TOKEN, "[REDACTED_GITHUB_TOKEN]");
  }
  return redacted;
}

console.log = function (...args: any[]) {
  const formatted = util.format(...args);
  process.stdout.write(redact(formatted) + "\n");
};

console.warn = function (...args: any[]) {
  const formatted = util.format(...args);
  process.stderr.write(redact(formatted) + "\n");
};

console.error = function (...args: any[]) {
  const formatted = util.format(...args);
  process.stderr.write(redact(formatted) + "\n");
};
