import { redact } from "../env.js";

export function redactToken(str: string): string {
  return redact(str);
}
