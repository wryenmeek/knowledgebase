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
import { redactToken } from "./github/logging.js";

// Validate required environment variables on startup
const JULES_API_KEY = process.env.JULES_API_KEY;
const GITHUB_TOKEN = process.env.GITHUB_TOKEN;

if (!JULES_API_KEY) {
  process.stderr.write("❌ JULES_API_KEY environment variable is required.\n");
  process.exit(1);
}

if (!GITHUB_TOKEN) {
  process.stderr.write("❌ GITHUB_TOKEN environment variable is required.\n");
  process.exit(1);
}

export { JULES_API_KEY, GITHUB_TOKEN };

// Redact logs globally
const originalLog = console.log;
const originalError = console.error;
const originalWarn = console.warn;
const originalInfo = console.info;

console.log = (...args: any[]) => {
  const formatted = util.format(...args);
  originalLog(redactToken(formatted));
};

console.error = (...args: any[]) => {
  const formatted = util.format(...args);
  originalError(redactToken(formatted));
};

console.warn = (...args: any[]) => {
  const formatted = util.format(...args);
  originalWarn(redactToken(formatted));
};

console.info = (...args: any[]) => {
  const formatted = util.format(...args);
  originalInfo(redactToken(formatted));
};
