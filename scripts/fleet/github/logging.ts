import { sanitizeErrorText } from "./mutation-diagnostics.js";

export function redactToken(str: string): string {
  return sanitizeErrorText(str);
}
