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

import path from "node:path";

const FLEET_DATE_PATTERN = /^\d{4}_\d{2}_\d{2}$/;

export function resolveFleetDir(root: string, fleetDate: string): string {
  if (!FLEET_DATE_PATTERN.test(fleetDate)) {
    throw new Error(
      `Invalid FLEET_PENDING_DATE "${fleetDate}"; expected YYYY_MM_DD format.`
    );
  }

  const fleetRoot = path.resolve(root, ".fleet");
  const fleetDir = path.resolve(fleetRoot, fleetDate);
  const relative = path.relative(fleetRoot, fleetDir);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(
      `Resolved fleet directory escapes .fleet root for FLEET_PENDING_DATE "${fleetDate}".`
    );
  }

  return fleetDir;
}

