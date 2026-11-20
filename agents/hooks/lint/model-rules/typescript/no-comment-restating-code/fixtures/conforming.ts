/** Conforming cases for the no-comment-restating-code eval; labels are in ../expect.yml. Never imported or run. */

export function readLines(text: string): string[] {
  // Windows editors save CRLF, and the parser below splits on LF only.
  return text.replaceAll("\r\n", "\n").split("\n");
}

export async function release(lock: { readonly free: () => Promise<void> }, log: (line: string) => void): Promise<void> {
  // Log before freeing: another process may take the lock and rotate the log at once.
  log("releasing");
  await lock.free();
}

export function sortByKey<T>(items: readonly T[], key: (item: T) => number): T[] {
  // Array.prototype.sort is stable since ES2019, and callers rely on equal keys keeping their order.
  return [...items].sort((left, right) => key(left) - key(right));
}

export const backoffMs = (retries: number): number => {
  // Capped at 8 retries: the gateway drops the connection after 30 s (#142).
  return 2 ** Math.min(retries, 8) * 100;
};

/** Prices are kept in cents, so the tax is rounded to a whole cent. */
export const withTaxCents = (cents: number): number => Math.round(cents * 1.1);
