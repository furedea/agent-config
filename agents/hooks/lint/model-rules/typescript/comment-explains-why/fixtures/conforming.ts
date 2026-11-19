/** Conforming cases for the comment-explains-why eval; labels are in ../expect.yml. Never imported or run. */

export function readLines(text: string): string[] {
  // Windows editors save CRLF, and the parser below splits on LF only.
  return text.replaceAll("\r\n", "\n").split("\n");
}

// The API rejects pages larger than 100 items (#142), so stay well below it.
export const PAGE_SIZE = 50;

export async function release(lock: { readonly free: () => Promise<void> }, log: (line: string) => void): Promise<void> {
  // Log before freeing: another process may take the lock and rotate the log at once.
  log("releasing");
  await lock.free();
}

export const backoffMs = (retries: number): number => {
  // TODO(#88): add jitter once the load test shows synchronized retries.
  return 2 ** retries * 100;
};
