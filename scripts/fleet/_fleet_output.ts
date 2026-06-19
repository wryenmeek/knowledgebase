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

import {
  getSanitizedErrorMessage,
  MutationFailureError,
  PreflightFailureError,
  type SanitizedErrorEnvelope,
} from "./github/mutation-diagnostics.js";

export interface FleetFatalMessages {
  preflight: string;
  mutation: string;
  genericPrefix: string;
}

export function logMutationAttemptFailure(
  message: string,
  envelope: SanitizedErrorEnvelope
): void {
  console.error(message);
  console.error(JSON.stringify(envelope));
}

export function handleFleetFatalError(
  error: unknown,
  messages: FleetFatalMessages
): never {
  if (error instanceof PreflightFailureError) {
    console.error(messages.preflight);
    console.error(JSON.stringify(error.envelope));
    process.exit(1);
  }

  if (error instanceof MutationFailureError) {
    if (error.terminalEnvelope.classification === "quota_saturation") {
      console.log(
        "::warning::Jules session quota saturated; Fleet run skipped this cycle. Re-run after quota resets."
      );
      console.log(JSON.stringify(error.terminalEnvelope));
      process.exit(0);
    }
    console.error(messages.mutation);
    console.error(JSON.stringify(error.terminalEnvelope));
    process.exit(1);
  }

  console.error(`${messages.genericPrefix}${getSanitizedErrorMessage(error)}`);
  process.exit(1);
}
