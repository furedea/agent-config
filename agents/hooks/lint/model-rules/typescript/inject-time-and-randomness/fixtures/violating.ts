/** Violating cases for the inject-time-and-randomness eval; labels are in ../expect.yml. Never imported or run. */

import { randomUUID } from "node:crypto";

export function isExpired(token: { readonly expiresAtMs: number }): boolean {
  return token.expiresAtMs < Date.now();
}

export function createSession(userId: string): Session {
  return { id: randomUUID(), userId, createdAt: new Date(), ttlMs: 3600_000 };
}

export const pickWinner = (entries: readonly string[]): string | undefined =>
  entries[Math.floor(Math.random() * entries.length)];

export function daysUntil(deadline: Date): number {
  const today = new Date;
  return Math.ceil((deadline.getTime() - today.getTime()) / 86_400_000);
}
