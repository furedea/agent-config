/** Violating cases for the function-single-purpose eval; labels are in ../expect.yml. Never imported or run. */

import { writeFileSync } from "node:fs";

export async function handleSignup(body: Uint8Array, db: Database, mailer: Mailer): Promise<number> {
  const text = new TextDecoder().decode(body);
  const fields = Object.fromEntries(text.split("&").map((pair) => pair.split("=").map(decodeURIComponent)));
  if (!fields.email?.includes("@") || (fields.password ?? "").length < 12) {
    return 400;
  }
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const hash = await crypto.subtle.digest("SHA-256", new Uint8Array([...salt, ...new TextEncoder().encode(fields.password)]));
  await db.insert("users", { email: fields.email, salt, hash: new Uint8Array(hash) });
  await mailer.send(fields.email, `<html><body><h1>Welcome ${fields.email.split("@")[0]}</h1></body></html>`);
  return 201;
}

export function writeReport(orders: readonly Order[], path: string): void {
  const totals = new Map<string, number>();
  for (const order of orders) {
    totals.set(order.region, (totals.get(order.region) ?? 0) + order.total);
  }
  let csv = "region,total\n";
  for (const [region, total] of totals) {
    csv += `${region.padEnd(12)},${(total / 100).toFixed(2).padStart(10)}\n`;
  }
  writeFileSync(path, csv);
}

export class Mirror {
  constructor(private readonly remote: Remote, private readonly store: Store) {}

  async sync(): Promise<void> {
    const response = await this.remote.fetchIndex();
    const header = response.slice(0, 16);
    const version = (header[0]! << 8) | header[1]!;
    const count = new DataView(header.buffer).getUint32(4);
    await this.store.prepare(version);
    await this.store.copy(response.slice(16), count);
    await this.store.commit();
  }
}

export const importContacts = async (text: string, db: Database): Promise<void> => {
  for (const line of text.trim().split("\n").slice(1)) {
    const cells = line.split(",").map((cell) => cell.trim().replace(/^"|"$/g, ""));
    await db.insert("contacts", { name: cells[0], phone: cells[1]?.replace(/[^0-9+]/g, "") });
  }
  await db.insert("audit", { action: "import", at: new Date().toISOString() });
};
