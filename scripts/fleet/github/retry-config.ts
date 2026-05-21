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

export const DEFAULT_MAX_REDISPATCH_RETRIES = 2;
export const MAX_REDISPATCH_RETRIES = 10;

export function resolveMaxRedispatchRetries(rawValue: string | undefined): number {
  if (!rawValue || rawValue.trim().length === 0) {
    return DEFAULT_MAX_REDISPATCH_RETRIES;
  }
  return Number(rawValue);
}

export function validateMaxRedispatchRetries(maxRetries: number): string | null {
  if (!Number.isInteger(maxRetries) || maxRetries < 0 || maxRetries > MAX_REDISPATCH_RETRIES) {
    return `FLEET_MAX_RETRIES must be an integer between 0 and ${MAX_REDISPATCH_RETRIES}; received "${String(
      maxRetries
    )}".`;
  }
  return null;
}
