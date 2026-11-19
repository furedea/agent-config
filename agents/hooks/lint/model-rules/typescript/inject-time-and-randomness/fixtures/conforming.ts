/** Conforming cases for the inject-time-and-randomness eval; labels are in ../expect.yml. Never imported or run. */

import { randomInt, type Rng } from "./rng";

export function main(argv: readonly string[]): void {
  run(argv, { now: () => Date.now(), rng: Math.random });
}

export function timed<T>(label: string, work: () => T, log: (line: string) => void): T {
  const start = Date.now();
  const result = work();
  log(`${label} took ${Date.now() - start} ms`);
  return result;
}

export function shuffle<T>(items: readonly T[], rng: Rng): T[] {
  const result = [...items];
  for (let index = result.length - 1; index > 0; index -= 1) {
    const other = randomInt(rng, index + 1);
    [result[index], result[other]] = [result[other]!, result[index]!];
  }
  return result;
}

export const systemClock: Clock = {
  now: () => new Date(),
};
