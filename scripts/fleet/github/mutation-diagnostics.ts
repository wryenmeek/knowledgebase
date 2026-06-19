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

const SECRET_PLACEHOLDER = "***REDACTED***";
const MAX_ERROR_MESSAGE_LENGTH = 1_000;
const DEFAULT_RETRY_BASE_DELAY_MS = 2_000;
const DEFAULT_RETRY_MAX_DELAY_MS = 8_000;
const MAX_MUTATION_ATTEMPTS = 5;

export const DEFAULT_MUTATION_MAX_ATTEMPTS = 3;

export const MUTATION_EXECUTION_CONTRACT = Object.freeze({
  first_pass_target: "diagnose_and_unblock",
  post_retry_behavior: "retry_then_hard_fail_with_diagnostics",
  diagnostic_detail: "sanitized_error_envelope",
} as const);

export type MutationErrorClass =
  | "failed_precondition"
  | "quota_saturation"
  | "auth"
  | "permission"
  | "rate_limit"
  | "network"
  | "unknown";

/**
 * Account-binding signals that indicate a genuine FAILED_PRECONDITION (hard-fail).
 * If none of these are present in a FAILED_PRECONDITION body, the error is
 * reclassified as quota_saturation (soft-warn, exit 0).
 * Reversibility: remove this constant and revert classifyFromSignals to always
 * return "failed_precondition" for FAILED_PRECONDITION bodies.
 */
const ACCOUNT_BINDING_RE = /GOOGLE ACCOUNT|GITHUB APP/i;

interface MutationCategoryDetails {
  readonly retryable: boolean;
  readonly hint: string;
  readonly rootCausePath: readonly string[];
}

const MUTATION_CATEGORY_DETAILS: Record<MutationErrorClass, MutationCategoryDetails> = {
  failed_precondition: {
    retryable: true,
    hint: "Validate repo/base-branch preconditions and retry. If still failing, escalate with this sanitized envelope.",
    rootCausePath: [
      "Confirm JULES_API_KEY and GITHUB_TOKEN are present in environment.",
      "Confirm source.github is owner/repo and FLEET_BASE_BRANCH points to an existing branch.",
      "Retry bounded attempts to absorb transient Jules precondition lag.",
      "If retries are exhausted, escalate provider-side with sanitized_error_envelope.",
    ],
  },
  quota_saturation: {
    retryable: false,
    hint: "Jules per-account session quota saturated. Fleet run is skipped; re-run after quota resets (typically within 24 hours). No code or configuration change is needed.",
    rootCausePath: [
      "Per-account Jules session cap reached; no account-binding error signal was present in the response body.",
      "This is a transient quota condition — no code or configuration change is needed.",
      "Re-run fleet dispatch after quota resets (typically within 24 hours).",
      "If saturation persists beyond 48 hours, escalate with sanitized_error_envelope evidence.",
    ],
  },
  auth: {
    retryable: false,
    hint: "Authentication failed. Verify JULES_API_KEY validity and GitHub token availability.",
    rootCausePath: [
      "Check JULES_API_KEY is present and not expired/revoked.",
      "Check the runtime loaded the expected secrets.",
      "Re-run only after credential correction.",
    ],
  },
  permission: {
    retryable: false,
    hint: "Permission denied. Verify repository access and token scopes before retrying.",
    rootCausePath: [
      "Check token scopes include required repository permissions.",
      "Check repository/org policy allows the Jules mutation.",
      "Re-run only after permission changes are applied.",
    ],
  },
  rate_limit: {
    retryable: true,
    hint: "Rate limit exceeded. Retry will use deterministic backoff.",
    rootCausePath: [
      "Confirm provider/API quota state.",
      "Allow backoff retries to complete.",
      "If still limited, increase interval or adjust automation load.",
    ],
  },
  network: {
    retryable: true,
    hint: "Transient network/service failure detected. Retry will use deterministic backoff.",
    rootCausePath: [
      "Check network reachability to Jules service.",
      "Retry bounded attempts for transient transport failures.",
      "Escalate if persistent with sanitized_error_envelope evidence.",
    ],
  },
  unknown: {
    retryable: false,
    hint: "Unknown mutation failure. Inspect sanitized envelope and classify manually.",
    rootCausePath: [
      "Review sanitized_error_envelope message/code/status.",
      "Compare against known classes (FAILED_PRECONDITION/auth/permission/rate/network).",
      "Escalate if no deterministic local fix exists.",
    ],
  },
};

export interface MutationClassification {
  category: MutationErrorClass;
  retryable: boolean;
  statusCode: number | null;
  errorCode: string | null;
  message: string;
  hint: string;
  rootCausePath: readonly string[];
}

export interface SanitizedErrorEnvelope {
  contract: typeof MUTATION_EXECUTION_CONTRACT;
  operation: string;
  attempt: number;
  max_attempts: number;
  classification: MutationErrorClass;
  retryable: boolean;
  retrying: boolean;
  retry_delay_ms: number | null;
  status_code: number | null;
  error_code: string | null;
  message: string;
  hint: string;
  root_cause_path: readonly string[];
}

export interface PreflightFailureEnvelope {
  contract: typeof MUTATION_EXECUTION_CONTRACT;
  operation: string;
  classification: "preflight";
  failures: string[];
}

export class PreflightFailureError extends Error {
  readonly envelope: PreflightFailureEnvelope;

  constructor(envelope: PreflightFailureEnvelope) {
    super(`Preflight failed for ${envelope.operation}: ${envelope.failures.join(" | ")}`);
    this.name = "PreflightFailureError";
    this.envelope = envelope;
  }
}

export class MutationFailureError extends Error {
  readonly operation: string;
  readonly attempts: SanitizedErrorEnvelope[];

  constructor(operation: string, attempts: SanitizedErrorEnvelope[]) {
    const terminal = attempts[attempts.length - 1];
    const classification = terminal?.classification ?? "unknown";
    super(
      `Mutation "${operation}" hard-failed after ${attempts.length} attempt(s) (${classification}).`
    );
    this.name = "MutationFailureError";
    this.operation = operation;
    this.attempts = attempts;
  }

  get terminalEnvelope(): SanitizedErrorEnvelope {
    return this.attempts[this.attempts.length - 1];
  }
}

export interface MutationPreflightOptions {
  operation: string;
  repoFullName: string;
  baseBranch: string;
  maxAttempts: number;
  requireGitHubToken?: boolean;
}

export interface RunMutationWithDiagnosticsOptions<T> {
  operation: string;
  maxAttempts: number;
  run: () => Promise<T>;
  onAttemptFailure?: (envelope: SanitizedErrorEnvelope) => void;
  retryBaseDelayMs?: number;
  retryMaxDelayMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function toStringValue(value: unknown): string | null {
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  return null;
}

function toNumberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function truncate(value: string): string {
  return value.length <= MAX_ERROR_MESSAGE_LENGTH
    ? value
    : `${value.slice(0, MAX_ERROR_MESSAGE_LENGTH)}…<truncated>`;
}

function normalizeErrorMessage(error: unknown): string {
  if (error instanceof Error && typeof error.message === "string") {
    return error.message;
  }

  const record = asRecord(error);
  if (record) {
    const directMessage = toStringValue(record.message);
    if (directMessage) {
      return directMessage;
    }

    const nestedError = asRecord(record.error);
    const nestedMessage = toStringValue(nestedError?.message);
    if (nestedMessage) {
      return nestedMessage;
    }

    const cause = asRecord(record.cause);
    const causeMessage = toStringValue(cause?.message);
    if (causeMessage) {
      return causeMessage;
    }
  }

  return String(error);
}

function extractStatusCode(error: unknown): number | null {
  const record = asRecord(error);
  if (!record) {
    return null;
  }

  const nestedError = asRecord(record.error);
  const response = asRecord(record.response);
  const cause = asRecord(record.cause);

  const candidates = [
    toNumberValue(record.status),
    toNumberValue(record.statusCode),
    toNumberValue(nestedError?.status),
    toNumberValue(nestedError?.statusCode),
    toNumberValue(response?.status),
    toNumberValue(cause?.status),
    toNumberValue(cause?.statusCode),
  ];

  for (const candidate of candidates) {
    if (candidate !== null) {
      return candidate;
    }
  }
  return null;
}

function extractErrorCode(error: unknown, upperMessage: string): string | null {
  const record = asRecord(error);
  const nestedError = asRecord(record?.error);
  const response = asRecord(record?.response);
  const cause = asRecord(record?.cause);

  const candidates = [
    toStringValue(record?.code),
    toStringValue(nestedError?.code),
    toStringValue(response?.code),
    toStringValue(cause?.code),
  ];

  for (const candidate of candidates) {
    if (candidate) {
      return candidate;
    }
  }

  const canonicalCodes = [
    "FAILED_PRECONDITION",
    "UNAUTHENTICATED",
    "PERMISSION_DENIED",
    "RESOURCE_EXHAUSTED",
  ];

  for (const code of canonicalCodes) {
    if (upperMessage.includes(code)) {
      return code;
    }
  }

  return null;
}

function classifyFromSignals(statusCode: number | null, upper: string): MutationErrorClass {
  if (upper.includes("FAILED_PRECONDITION") || (statusCode === 400 && upper.includes("PRECONDITION"))) {
    // Account-binding signals (e.g. unregistered Google account, GitHub App mis-config)
    // represent a genuine hard-fail precondition that requires operator remediation.
    // A bare body with no such signal is quota saturation — soft-warn, not hard-fail.
    return ACCOUNT_BINDING_RE.test(upper) ? "failed_precondition" : "quota_saturation";
  }
  if (
    statusCode === 401 ||
    upper.includes("UNAUTHENTICATED") ||
    upper.includes("INVALID_API_KEY") ||
    upper.includes("AUTHENTICATION")
  ) {
    return "auth";
  }
  if (statusCode === 403 || upper.includes("PERMISSION_DENIED") || upper.includes("FORBIDDEN")) {
    return "permission";
  }
  if (
    statusCode === 429 ||
    upper.includes("RESOURCE_EXHAUSTED") ||
    upper.includes("RATE_LIMIT") ||
    upper.includes("TOO MANY REQUESTS")
  ) {
    return "rate_limit";
  }
  if (
    upper.includes("ETIMEDOUT") ||
    upper.includes("ECONNRESET") ||
    upper.includes("ENOTFOUND") ||
    upper.includes("EHOSTUNREACH") ||
    upper.includes("NETWORK") ||
    upper.includes("FETCH FAILED") ||
    (statusCode !== null && statusCode >= 500)
  ) {
    return "network";
  }
  return "unknown";
}

function computeRetryDelayMs(
  attempt: number,
  retryBaseDelayMs: number,
  retryMaxDelayMs: number
): number {
  return Math.min(retryBaseDelayMs * attempt, retryMaxDelayMs);
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function envSecretValues(): string[] {
  return [process.env.JULES_API_KEY, process.env.GITHUB_TOKEN].filter(
    (value): value is string => Boolean(value && value.length > 0)
  );
}

export function redactSecrets(raw: string): string {
  let sanitized = raw;

  for (const secret of envSecretValues()) {
    sanitized = sanitized.split(secret).join(SECRET_PLACEHOLDER);
  }

  sanitized = sanitized
    .replace(
      /\b(JULES_API_KEY|GITHUB_TOKEN)\s*[:=]\s*['"]?[^\s'"]+['"]?/gi,
      `$1=${SECRET_PLACEHOLDER}`
    )
    .replace(
      /\b(authorization)\s*:\s*bearer\s+[a-z0-9._-]+/gi,
      `$1: Bearer ${SECRET_PLACEHOLDER}`
    )
    .replace(/\bbearer\s+[a-z0-9._-]{8,}/gi, `Bearer ${SECRET_PLACEHOLDER}`);

  return sanitized;
}

export function sanitizeErrorText(raw: string): string {
  return truncate(redactSecrets(raw));
}

export function getSanitizedErrorMessage(error: unknown): string {
  return sanitizeErrorText(normalizeErrorMessage(error));
}

export function classifyMutationError(error: unknown): MutationClassification {
  const message = getSanitizedErrorMessage(error);
  const statusCode = extractStatusCode(error);
  const upper = message.toUpperCase();
  const errorCode = extractErrorCode(error, upper);
  const category = classifyFromSignals(statusCode, `${upper} ${errorCode ?? ""}`);
  const details = MUTATION_CATEGORY_DETAILS[category];

  return {
    category,
    retryable: details.retryable,
    statusCode,
    errorCode,
    message,
    hint: details.hint,
    rootCausePath: details.rootCausePath,
  };
}

function toAttemptEnvelope(
  operation: string,
  attempt: number,
  maxAttempts: number,
  classification: MutationClassification,
  retrying: boolean,
  retryDelayMs: number | null
): SanitizedErrorEnvelope {
  return {
    contract: MUTATION_EXECUTION_CONTRACT,
    operation,
    attempt,
    max_attempts: maxAttempts,
    classification: classification.category,
    retryable: classification.retryable,
    retrying,
    retry_delay_ms: retryDelayMs,
    status_code: classification.statusCode,
    error_code: classification.errorCode,
    message: classification.message,
    hint: classification.hint,
    root_cause_path: classification.rootCausePath,
  };
}

export function resolveMutationMaxAttempts(rawValue: string | undefined): number {
  if (!rawValue || rawValue.trim().length === 0) {
    return DEFAULT_MUTATION_MAX_ATTEMPTS;
  }
  return Number(rawValue);
}

function validateMaxAttempts(maxAttempts: number): string | null {
  if (!Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > MAX_MUTATION_ATTEMPTS) {
    return `FLEET_MUTATION_MAX_ATTEMPTS must be an integer between 1 and ${MAX_MUTATION_ATTEMPTS}; received "${String(
      maxAttempts
    )}".`;
  }
  return null;
}

export function assertMutationPreflight(options: MutationPreflightOptions): void {
  const failures: string[] = [];

  if (!process.env.JULES_API_KEY || process.env.JULES_API_KEY.trim().length === 0) {
    failures.push("Missing required environment variable: JULES_API_KEY.");
  }

  if (
    options.requireGitHubToken &&
    (!process.env.GITHUB_TOKEN || process.env.GITHUB_TOKEN.trim().length === 0)
  ) {
    failures.push("Missing required environment variable: GITHUB_TOKEN.");
  }

  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(options.repoFullName)) {
    failures.push(
      `Invalid repository identifier "${sanitizeErrorText(options.repoFullName)}"; expected owner/repo.`
    );
  }

  if (options.baseBranch.trim().length === 0 || /\s/.test(options.baseBranch)) {
    failures.push(
      `Invalid base branch "${sanitizeErrorText(options.baseBranch)}"; must be non-empty and contain no whitespace.`
    );
  }

  const maxAttemptsFailure = validateMaxAttempts(options.maxAttempts);
  if (maxAttemptsFailure) {
    failures.push(maxAttemptsFailure);
  }

  if (failures.length > 0) {
    throw new PreflightFailureError({
      contract: MUTATION_EXECUTION_CONTRACT,
      operation: options.operation,
      classification: "preflight",
      failures,
    });
  }
}

export async function runMutationWithDiagnostics<T>(
  options: RunMutationWithDiagnosticsOptions<T>
): Promise<T> {
  const maxAttemptsFailure = validateMaxAttempts(options.maxAttempts);
  if (maxAttemptsFailure) {
    throw new Error(maxAttemptsFailure);
  }

  const attemptEnvelopes: SanitizedErrorEnvelope[] = [];
  const retryBaseDelayMs = options.retryBaseDelayMs ?? DEFAULT_RETRY_BASE_DELAY_MS;
  const retryMaxDelayMs = options.retryMaxDelayMs ?? DEFAULT_RETRY_MAX_DELAY_MS;
  const sleep = options.sleep ?? defaultSleep;

  for (let attempt = 1; attempt <= options.maxAttempts; attempt++) {
    try {
      return await options.run();
    } catch (error) {
      const classification = classifyMutationError(error);
      const retrying = classification.retryable && attempt < options.maxAttempts;
      const retryDelayMs = retrying
        ? computeRetryDelayMs(attempt, retryBaseDelayMs, retryMaxDelayMs)
        : null;
      const envelope = toAttemptEnvelope(
        options.operation,
        attempt,
        options.maxAttempts,
        classification,
        retrying,
        retryDelayMs
      );
      attemptEnvelopes.push(envelope);
      options.onAttemptFailure?.(envelope);

      if (retrying && retryDelayMs !== null) {
        await sleep(retryDelayMs);
        continue;
      }

      throw new MutationFailureError(options.operation, attemptEnvelopes);
    }
  }

  throw new MutationFailureError(options.operation, attemptEnvelopes);
}
