import { redactSecrets } from "./mutation-diagnostics.js";

export function redactToken(str: string): string {
  return redactSecrets(str);
}
