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

import type { IssueAnalysis } from "../types.js";

export function validateTaskOwnership(analysis: IssueAnalysis): void {
  const taskIds = new Set<string>();
  const claimed = new Map<string, string>();

  for (const task of analysis.tasks) {
    if (taskIds.has(task.id)) {
      throw new Error(`Duplicate task id "${task.id}" found in manifest. Task IDs must be unique.`);
    }
    taskIds.add(task.id);

    const allFiles = [...task.files, ...task.new_files, ...(task.test_files ?? [])];
    for (const file of allFiles) {
      const existing = claimed.get(file);
      if (existing) {
        throw new Error(
          `Ownership conflict: "${file}" claimed by both "${existing}" and "${task.id}". These tasks must be merged.`
        );
      }
      claimed.set(file, task.id);
    }
  }
}
