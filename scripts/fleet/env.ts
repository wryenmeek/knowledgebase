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

console.log = (...args: any[]) => {
  process.stdout.write(redactToken(util.format(...args)) + "\n");
};

console.error = (...args: any[]) => {
  process.stderr.write(redactToken(util.format(...args)) + "\n");
};

console.warn = (...args: any[]) => {
  process.stderr.write(redactToken(util.format(...args)) + "\n");
};
