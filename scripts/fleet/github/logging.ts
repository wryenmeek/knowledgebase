export function redactToken(str: string): string {
  if (!process.env.GITHUB_TOKEN) return str;
  return str.replaceAll(process.env.GITHUB_TOKEN, '***REDACTED***');
}
