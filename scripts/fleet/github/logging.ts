export function redactToken(str: string): string {
  let redacted = str;
  if (process.env.GITHUB_TOKEN) {
    redacted = redacted.replaceAll(process.env.GITHUB_TOKEN, '***REDACTED***');
  }
  if (process.env.JULES_API_KEY) {
    redacted = redacted.replaceAll(process.env.JULES_API_KEY, '***REDACTED***');
  }
  return redacted;
}
