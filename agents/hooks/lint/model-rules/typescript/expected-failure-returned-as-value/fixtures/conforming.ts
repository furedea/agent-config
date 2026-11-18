/** Conforming cases for the expected-failure-returned-as-value eval; labels are in ../expect.yml. Never imported or run. */

import { readFile } from "node:fs/promises";

export function assertNever(value: never): never {
  throw new Error(`unexpected variant: ${JSON.stringify(value)}`);
}

export function chunk<T>(items: readonly T[], size: number): T[][] {
  if (!Number.isInteger(size) || size < 1) {
    throw new RangeError(`chunk: size must be a positive integer, got ${size}`);
  }
  const chunks: T[][] = [];
  for (let start = 0; start < items.length; start += size) {
    chunks.push(items.slice(start, start + size));
  }
  return chunks;
}

export async function readConfig(path: string): Promise<Result<Config, "missing" | "invalid">> {
  let text: string;
  try {
    text = await readFile(path, "utf8");
  } catch (error) {
    if (isNotFound(error)) {
      return { ok: false, error: "missing" };
    }
    throw new Error(`read config ${path}`, { cause: error });
  }
  return parseConfig(text);
}

export class Ledger {
  private balance = 0;

  deposit(cents: number): void {
    this.settle(this.balance + cents);
  }

  private settle(next: number): void {
    if (!Number.isSafeInteger(next)) {
      throw new Error(`settle ledger: balance ${next} is no longer an exact integer`);
    }
    this.balance = next;
  }
}
