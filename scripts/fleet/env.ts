import util from "node:util";
import { redactToken } from "./github/logging.js";

export interface FleetEnvRequirements {
  requireJulesApiKey?: boolean;
  requireGitHubToken?: boolean;
  installConsoleRedaction?: boolean;
}

const DEFAULT_REQUIREMENTS: Required<FleetEnvRequirements> = {
  requireJulesApiKey: false,
  requireGitHubToken: false,
  installConsoleRedaction: true,
};

function hasValue(value: string | undefined): boolean {
  return Boolean(value && value.trim().length > 0);
}

function collectMissingVariables(requirements: Required<FleetEnvRequirements>): string[] {
  const missingVariables: string[] = [];
  if (requirements.requireJulesApiKey && !hasValue(process.env.JULES_API_KEY)) {
    missingVariables.push("JULES_API_KEY");
  }
  if (requirements.requireGitHubToken && !hasValue(process.env.GITHUB_TOKEN)) {
    missingVariables.push("GITHUB_TOKEN");
  }
  return missingVariables;
}

let consoleRedactionInstalled = false;

export function installConsoleRedaction(): void {
  if (consoleRedactionInstalled) {
    return;
  }

  const originalLog = console.log.bind(console);
  console.log = (...args: any[]) => {
    originalLog(redactToken(util.format(...args)));
  };

  const originalError = console.error.bind(console);
  console.error = (...args: any[]) => {
    originalError(redactToken(util.format(...args)));
  };

  const originalWarn = console.warn.bind(console);
  console.warn = (...args: any[]) => {
    originalWarn(redactToken(util.format(...args)));
  };

  consoleRedactionInstalled = true;
}

export function assertFleetEnvironment(requirements: FleetEnvRequirements = {}): void {
  const resolvedRequirements = {
    ...DEFAULT_REQUIREMENTS,
    ...requirements,
  };
  const missingVariables = collectMissingVariables(resolvedRequirements);
  if (missingVariables.length > 0) {
    throw new Error(
      `Missing required environment variable${missingVariables.length === 1 ? "" : "s"}: ${missingVariables.join(", ")}.`
    );
  }
  if (resolvedRequirements.installConsoleRedaction) {
    installConsoleRedaction();
  }
}
