import * as util from "node:util";

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const JULES_API_KEY = process.env.JULES_API_KEY;

if (!GITHUB_TOKEN) {
  process.stdout.write("❌ GITHUB_TOKEN environment variable is required.\n");
  process.exit(1);
}

if (!JULES_API_KEY) {
  process.stdout.write("❌ JULES_API_KEY environment variable is required.\n");
  process.exit(1);
}

export { GITHUB_TOKEN, JULES_API_KEY };

export function redactToken(str: string): string {
  let redacted = str;
  if (GITHUB_TOKEN) {
    redacted = redacted.replaceAll(GITHUB_TOKEN, "***REDACTED***");
  }
  if (JULES_API_KEY) {
    redacted = redacted.replaceAll(JULES_API_KEY, "***REDACTED***");
  }
  return redacted;
}

export function setupRedactedLogging(): void {
  console.log = (...args: any[]) => {
    const formatted = util.format(...args);
    process.stdout.write(redactToken(formatted) + "\n");
  };

  console.error = (...args: any[]) => {
    const formatted = util.format(...args);
    process.stderr.write(redactToken(formatted) + "\n");
  };

  console.warn = (...args: any[]) => {
    const formatted = util.format(...args);
    process.stderr.write(redactToken(formatted) + "\n");
  };
}
