import util from "node:util";
import { redactToken } from "./github/logging.js";

export const JULES_API_KEY = process.env.JULES_API_KEY as string;
export const GITHUB_TOKEN = process.env.GITHUB_TOKEN as string;

if (!JULES_API_KEY) {
  console.error("❌ JULES_API_KEY environment variable is required.");
  process.exit(1);
}

if (!GITHUB_TOKEN) {
  console.error("❌ GITHUB_TOKEN environment variable is required.");
  process.exit(1);
}

const originalLog = console.log;
console.log = (...args: any[]) => {
  originalLog(redactToken(util.format(...args)));
};

const originalError = console.error;
console.error = (...args: any[]) => {
  originalError(redactToken(util.format(...args)));
};

const originalWarn = console.warn;
console.warn = (...args: any[]) => {
  originalWarn(redactToken(util.format(...args)));
};
